from ..base import BaseSearch
import requests
import threading
import time
from typing import List, Dict, Any
import json
import re
import urllib.parse

class PlanorgSearch(BaseSearch):
    """
    planorg.cn 网页搜索实现，SSE流式接口，真链需二次POST save_url，支持多线程
    """
    API_URL = "https://v.planorg.cn/api/other/web_search"
    SAVE_URL = "https://v.planorg.cn/api/other/save_url"
    CACHE_TTL = 3600  # 1小时
    CACHE_CLEAN_INTERVAL = 3600  # 1小时

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

    def search(self, keyword: str) -> Dict[str, Any]:
        cache_key = keyword.strip()
        now = time.time()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached["timestamp"] < self.CACHE_TTL:
                return self._format_results(cached["results"], keyword)
        try:
            items = self._search_api(keyword)
            results = self._convert_results(items)
            with self._cache_lock:
                self._cache[cache_key] = {
                    "results": results,
                    "timestamp": time.time()
                }
            return self._format_results(results, keyword)
        except Exception as e:
            print(f"planorg API error: {str(e)}")
            return self._format_results([], keyword)

    def _search_api(self, keyword: str) -> List[Dict[str, Any]]:
        params = {
            "title": keyword,
            "is_type": 0
        }
        headers = {
            "accept": "text/event-stream",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "cache-control": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        cookies = {
            "PHPSESSID": "a0476b5169c42ba8f655a1a1d75eb5da",
            "__51uvsct__23kqyqxydKgZPU3F": "1",
            "__51vcke__23kqyqxydKgZPU3F": "d01d6191-1da7-5b83-9564-1debde0619dd",
            "__51vuft__23kqyqxydKgZPU3F": "1754294369330",
            "__vtins__23kqyqxydKgZPU3F": '{"sid": "b892af21-d2d2-5f7d-9b85-1dd452e1e616", "vd": 11, "stt": 873065, "dr": 10863, "expires": 1754297042393, "ct": 1754295242393}'
        }
        items = []
        resp = requests.get(self.API_URL, headers=headers, params=params, cookies=cookies, stream=True, timeout=15)
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
                items.append(obj)
            except Exception as e:
                print(f"planorg SSE parse error: {str(e)} line={data_str}")
                continue
        return items

    def _convert_results(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 1. 收集所有 (url, title, stoken)
        tasks = []
        for idx, item in enumerate(items):
            url = item.get("url", "")
            if not url:
                continue
            url = url.replace("\\/", "/")
            title = self._clean_html(item.get("title", ""))
            stoken = item.get("stoken", "")
            tasks.append({
                "idx": idx,
                "url": url,
                "title": title,
                "stoken": stoken,
                "is_type": item.get("is_type", 0)
            })

        # 2. 用线程池批量请求 save_url
        def fetch_real_link(task):
            save_headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://v.planorg.cn",
                "priority": "u=1, i",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            }
            save_cookies = {
                "PHPSESSID": "a0476b5169c42ba8f655a1a1d75eb5da",
                "__51uvsct__23kqyqxydKgZPU3F": "1",
                "__51vcke__23kqyqxydKgZPU3F": "d01d6191-1da7-5b83-9564-1debde0619dd",
                "__51vuft__23kqyqxydKgZPU3F": "1754294369330",
                "__vtins__23kqyqxydKgZPU3F": '{"sid": "b892af21-d2d2-5f7d-9b85-1dd452e1e616", "vd": 12, "stt": 1078845, "dr": 205780, "expires": 1754297248173, "ct": 1754295448173}'
            }
            # url 需 urlencode
            post_data = {
                "url": urllib.parse.quote(task["url"], safe=""),
                "title": task["title"]
            }
            try:
                resp = requests.post(
                    self.SAVE_URL,
                    headers=save_headers,
                    cookies=save_cookies,
                    data=json.dumps(post_data),
                    timeout=10
                )
                resp.raise_for_status()
                data = resp.json()
                # 兼容不同返回结构
                real_url = data.get("data", {}).get("final_url") or data.get("data", {}).get("url") or ""
                if not real_url:
                    # 兜底
                    real_url = data.get("data", "") if isinstance(data.get("data", ""), str) else ""
                return {
                    "idx": task["idx"],
                    "real_url": real_url,
                    "stoken": task["stoken"],
                    "title": task["title"],
                    "is_type": task["is_type"]
                }
            except Exception as e:
                print(f"save_url error: {str(e)} for url={task['url']}")
                return {
                    "idx": task["idx"],
                    "real_url": "",
                    "stoken": task["stoken"],
                    "title": task["title"],
                    "is_type": task["is_type"]
                }

        # 用线程池并发
        real_links = self._batch_fetch_details(tasks, fetch_real_link, max_workers=8)

        # 3. 组装最终结果
        results = []
        for item in real_links:
            real_url = item.get("real_url", "")
            if not real_url:
                continue
            link_type = self.detect_cloud_type(real_url)
            result = {
                "messageId": f"planorg-{item['idx']}",
                "title": item["title"],
                "pubDate": "",
                "content": item["title"],
                "image": "",
                "cloudLinks": [{
                    "link": real_url,
                    "cloudType": link_type,
                    "stoken": item.get("stoken", "")
                }],
                "tags": [],
                "magnetLink": "",
                "channel": "planorg",
                "channelId": "planorg"
            }
            results.append(result)
        return results

    def _batch_fetch_details(self, tasks, func, max_workers=8):
        """
        通用线程池批量处理工具，仿照 quarkso/roubuyaoqian
        """
        import concurrent.futures
        results = [None] * len(tasks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {executor.submit(func, task): i for i, task in enumerate(tasks)}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    results[idx] = result
                except Exception as e:
                    print(f"batch_fetch_details error: {str(e)}")
        # 过滤 None
        return [r for r in results if r]

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
                "id": "planorg",
                "name": "planorg",
                "index": 1030,
                "channelLogo": ""
            },
            "id": "planorg",
            "index": 1030,
            "total": len(results),
            "keyword": keyword
        }