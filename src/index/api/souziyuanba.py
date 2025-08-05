from ..base import BaseSearch
import requests
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import re
import json
import threading
import time

class SouziyuanbaSearch(BaseSearch):
    """
    搜资源吧 网页搜索实现，仿 quarkso.py，支持 NUXT_DATA 提取与直链POST
    """
    BASE_URL = "https://www.souziyuanba.com/sa"
    SAVE_URL = "https://www.souziyuanba.com/v1/resource_save"
    CACHE_TTL = 3600
    CACHE_CLEAN_INTERVAL = 3600

    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._last_clean_time = time.time()
        self._start_cache_cleaner()

    def _start_cache_cleaner(self):
        def cleaner():
            while True:
                time.sleep(self.CACHE_CLEAN_INTERVAL)
                with self._cache_lock:
                    self._cache.clear()
                    self._last_clean_time = time.time()
        t = threading.Thread(target=cleaner, daemon=True)
        t.start()

    def search(self, keyword: str, category: str = "综合三") -> Dict[str, Any]:
        cache_key = f"{keyword}|{category}"
        now = time.time()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached["timestamp"] < self.CACHE_TTL:
                return self._format_results(cached["results"], keyword)
        try:
            items, nuxt_data = self._search_html(keyword, category)
            results = self._convert_results(items, keyword, category, nuxt_data)
            with self._cache_lock:
                self._cache[cache_key] = {
                    "results": results,
                    "timestamp": time.time()
                }
            return self._format_results(results, keyword)
        except Exception as e:
            print(f"souziyuanba API error: {str(e)}")
            return self._format_results([], keyword)

    def _search_html(self, keyword: str, category: str) -> (List[Dict[str, Any]], Any):
        params = {
            "query": keyword,
            "category": category
        }
        headers = {
            "Referer": "https://www.souziyuanba.com/",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
        resp = requests.get(self.BASE_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        result_items = soup.find_all("div", class_="yp-network-search-result-item")
        results = []
        nuxt_data = self._extract_nuxt_data(soup)
        for item in result_items:
            try:
                # 标题
                h2 = item.find("h2", class_="yp-network-search-result-item-text-title")
                title = self._clean_html(h2.text) if h2 else ""
                # 描述
                desc_div = item.find("div", class_="yp-network-search-result-item-text-desc")
                content = self._clean_html(desc_div.text) if desc_div else ""
                # links 区块
                links_div = item.find("div", class_="yp-network-search-result-item-links")
                # 提取资源url和类型
                results.append({
                    "title": title,
                    "content": content,
                    "item_html": str(item)
                })
            except Exception as e:
                print(f"解析条目失败: {str(e)}")
                continue
        return results, nuxt_data

    def _extract_nuxt_data(self, soup: BeautifulSoup):
        script_tag = soup.find("script", {"id": "__NUXT_DATA__"})
        if script_tag:
            try:
                return json.loads(script_tag.string)
            except Exception as e:
                print(f"NUXT_DATA 解析失败: {str(e)}")
        return None

    def _resolve_resource_url_by_source(self, nuxt_json):
        """
        2 -> match source_name -> rows -> list,0 -> url
        """
        chain = [
            ('idx', 2),
            ('match', 'source_name'),
            ("origin", None),
            ("key", "rows"),
            ("origin", None),
        ]        
        def match_func(data, val):
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and val in k:
                        return v
            return None
        totol = self._resolve_json_chain(nuxt_json, chain, match_func, nuxt_json)
        print(totol)
        urls = list()
        for idx, _ in enumerate(totol):
            echain = chain + [("list", idx), ("origin", None), ('key', 'res_dict'), ('origin', None), ('key', 'quark'), ('origin', None), ('list', 0), ('origin', None), ('key', 'url'), ('origin', None)]
            url = self._resolve_json_chain(nuxt_json, echain, match_func, nuxt_json)
            urls.append(url)
        return urls

    def _convert_results(self, items: List[Dict[str, Any]], keyword: str, category: str, nuxt_data: any) -> List[Dict[str, Any]]:
        # 1. 收集所有 (url, pan_type, source_name)
        tasks = []
        urls = self._resolve_resource_url_by_source(nuxt_data)

        for idx, item in enumerate(items):
            # 优先用 NUXT_DATA 提取 url
            pan_url = urls[idx]
            tasks.append({
                "idx": idx,
                "url": pan_url,
                "pan_type": self.detect_cloud_type(pan_url),
                "source_name": category,
                "title": item.get("title", "")
            })
        # 2. 用父类线程池批量POST获取直链
        real_links = super()._batch_fetch_details(tasks, self._fetch_real_link, max_workers=8)
        # 3. 组装最终结果
        results = []
        for idx, item in enumerate(items):
            # 匹配 real_link
            real_link_obj = next((r for r in real_links if r["idx"] == idx), None)
            if real_link_obj and real_link_obj.get("real_url"):
                cloudLinks = [{
                    "link": real_link_obj["real_url"],
                    "cloudType": real_link_obj["pan_type"]
                }]
                results.append({
                    "messageId": f"souziyuanba-{idx}",
                    "title": item.get("title", ""),
                    "pubDate": "",
                    "content": item.get("content", ""),
                    "image": "",
                    "cloudLinks": cloudLinks,
                    "tags": [],
                    "magnetLink": "",
                    "channel": "搜资源吧",
                    "channelId": "souziyuanba"
                })
        return results

    def _fetch_real_link(self, task):
        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "content-type": "application/json",
            "origin": "https://www.souziyuanba.com",
            "priority": "u=1, i",
            "referer": f"https://www.souziyuanba.com/sa?query={urllib.parse.quote(task['title'])}&category={urllib.parse.quote(task['source_name'])}",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "site-id": "default",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        cookies = {
            # 仅示例，实际可补充
            "i18n_redirected": "zh"
        }
        post_data = {
            "source_name": task["source_name"],
            "url": task["url"],
            "pan_type": task["pan_type"],
            "filter_words": []
        }
        try:
            resp = requests.post(
                self.SAVE_URL,
                headers=headers,
                cookies=cookies,
                data=json.dumps(post_data),
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            real_url = data.get("data", {}).get("final_share_url")            
            return {
                "idx": task["idx"],
                "real_url": real_url,
                "pan_type": task["pan_type"]
            }
        except Exception as e:
            print(f"resource_save error: {str(e)} for url={task['url']}")
            return {
                "idx": task["idx"],
                "real_url": "",
                "pan_type": task["pan_type"]
            }

    # 不再实现 _batch_fetch_details 兜底，直接用父类
    def _clean_html(self, html: str) -> str:
        tags = [
            "<em>", "</em>", "<b>", "</b>", "<strong>", "</strong>",
            "<i>", "</i>", "<u>", "</u>", "<br>", "<br/>", "<br />"
        ]
        result = html or ""
        for tag in tags:
            result = result.replace(tag, "")
        result = re.sub(r'<[^>]+>', '', result)
        return result.strip()

    def _format_results(self, results: List[Dict[str, Any]], keyword: str) -> Dict[str, Any]:
        return {
            "list": results,
            "channelInfo": {
                "id": "souziyuanba",
                "name": "搜资源吧",
                "index": 1040,
                "channelLogo": ""
            },
            "id": "souziyuanba",
            "index": 1040,
            "total": len(results),
            "keyword": keyword
        }