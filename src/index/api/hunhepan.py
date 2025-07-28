from ..base import BaseSearch
import requests
import json
from typing import List, Dict, Any


class HunhepanSearch(BaseSearch):
    """混合盘搜索实现"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self.api_list = [
            ("hunhepan", "https://hunhepan.com/open/search/disk", "https://hunhepan.com/search"),
            ("qkpanso", "https://qkpanso.com/v1/search/disk", "https://qkpanso.com/search"),
            ("kuake8", "https://kuake8.com/v1/search/disk", "https://kuake8.com/search"),
        ]
        self.headers_base = {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索混合盘资源并返回结构化结果"""
        return self._search_with_api(keyword)

    def _map_cloud_type(self, disk_type: str) -> str:
        """映射云盘类型到统一格式
        Args:
            disk_type: 原始云盘类型字符串(如QUARK/ALY等)
        Returns:
            标准化后的云盘类型(quark/aliyun等)
        """
        CLOUD_TYPE_MAP = {
            "QUARK": "quark",
            "ALY": "aliyun",
            "BDY": "baidu",
            "TXY": "tencent",
            "CTY": "ctyun"
        }
        # 先尝试全大写匹配，再尝试小写匹配，最后返回原值小写
        return CLOUD_TYPE_MAP.get(
            disk_type.upper(),
            CLOUD_TYPE_MAP.get(disk_type.lower(), disk_type.lower())
        )
    def _search_with_api(self, keyword: str) -> List[Dict[str, Any]]:
        """并发请求多个API并合并去重"""
        import threading

        payload = {
            "q": keyword,
            "exact": True,
            "page": 1,
            "size": 30,
            "type": "",
            "time": "",
            "from": "web",
            "user_id": 0,
            "filter": True
        }

        results = []
        errors = []
        lock = threading.Lock()

        def fetch_api(api_name, api_url, referer):
            try:
                headers = self.headers_base.copy()
                headers['referer'] = referer
                resp = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 200:
                    with lock:
                        results.extend(data.get("data", {}).get("list", []))
                else:
                    with lock:
                        errors.append(f"{api_name} code: {data.get('code')} msg: {data.get('msg')}")
            except Exception as e:
                with lock:
                    errors.append(f"{api_name} error: {str(e)}")

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as executor:
            for api_name, api_url, referer in self.api_list:
                executor.submit(fetch_api, api_name, api_url, referer)

        # 去重，优先用 doc_id，否则用 link+disk_name
        seen = set()
        deduped = []
        for item in results:
            key = item.get("doc_id") or (item.get("link", "") + "|" + item.get("disk_name", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        return {
            "list": [{
                "messageId": item.get("doc_id", ""),
                "title": item.get("disk_name", "").replace("<em>", "").replace("</em>", ""),
                "pubDate": item.get("shared_time", ""),
                "content": item.get("files", ""),
                "image": "",
                "cloudLinks": [{
                    "link": item.get("link", ""),
                    "cloudType": self.detect_cloud_type(item.get("link", ""))
                }],
                "tags": [],
                "magnetLink": "",
                "channel": "混合盘",
                "channelId": "hunhepan"
            } for item in deduped],
            "channelInfo": {
                "id": "hunhepan",
                "name": "混合盘",
                "index": 1004,
                "channelLogo": ""
            },
            "id": "hunhepan",
            "index": 1004
        }