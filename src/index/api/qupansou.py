from ..base import BaseSearch
import requests
import threading
import time
from typing import List, Dict, Any
import json
import re

class QuPanSouSearch(BaseSearch):
    API_URL = "https://v.funletu.com/search"
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
        # 请求API
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
            print(f"qupansou API error: {str(e)}")
            return self._format_results([], keyword)

    def _search_api(self, keyword: str) -> List[Dict[str, Any]]:
        req_body = {
            "style": "get",
            "datasrc": "search",
            "query": {
                "id": "",
                "datetime": "",
                "courseid": 1,
                "categoryid": "",
                "filetypeid": "",
                "filetype": "",
                "reportid": "",
                "validid": "",
                "searchtext": keyword,
            },
            "page": {
                "pageSize": 1000,
                "pageIndex": 1,
            },
            "order": {
                "prop": "sort",
                "order": "desc",
            },
            "message": "请求资源列表数据",
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://pan.funletu.com/",
        }
        resp = requests.post(self.API_URL, headers=headers, json=req_body, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 200:
            raise Exception(f"API returned error: {data.get('message')}")
        return data.get("data", [])

    def _convert_results(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for item in items:
            url = item.get("url") or item.get("link") or ""
            if not url:
                continue
            link_type = self.detect_cloud_type(url)
            # 清理标题
            title = self._clean_html(item.get("title", ""))
            # 解析时间
            datetime = item.get("updatetime", "") or item.get("createtime", "")
            # 组装
            result = {
                "messageId": f"qupansou-{item.get('id', '')}",
                "title": title,
                "pubDate": datetime,
                "content": f"类别: {item.get('category', '')}, 文件类型: {item.get('filetype', '')}, 大小: {item.get('size', '')}",
                "image": "",
                "cloudLinks": [{
                    "link": url,
                    "cloudType": link_type,
                    "pwd": ""  # 趣盘搜API不返回密码
                }],
                "tags": [],
                "magnetLink": "",
                "channel": "趣盘搜",
                "channelId": "qupansou"
            }
            results.append(result)
        return results

    def _clean_html(self, html: str) -> str:
        # 替换常见HTML标签
        tags = [
            "<em>", "</em>", "<b>", "</b>", "<strong>", "</strong>",
            "<i>", "</i>", "<u>", "</u>", "<br>", "<br/>", "<br />"
        ]
        result = html or ""
        for tag in tags:
            result = result.replace(tag, "")
        # 去除所有剩余标签
        result = re.sub(r'<[^>]+>', '', result)
        return result.strip()

    def _format_results(self, results: List[Dict[str, Any]], keyword: str) -> Dict[str, Any]:
        return {
            "list": results,
            "channelInfo": {
                "id": "qupansou",
                "name": "趣盘搜",
                "index": 1021,
                "channelLogo": ""
            },
            "id": "qupansou",
            "index": 1021,
            "total": len(results),
            "keyword": keyword
        }