from ..base import BaseSearch
import requests
import json
from typing import List, Dict, Any


class HunhepanSearch(BaseSearch):
    """混合盘搜索实现"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self.base_url = "https://hunhepan.com/v1/search"
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0'
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
        """通过API搜索"""
        payload = {
            "q": keyword,
            "exact": False,
            "page": 1,
            "size": 15,
            "type": "",
            "time": "",
            "from": "web",
            "user_id": 0,
            "filter": True
        }

        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 200:
                return []

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
                } for item in data.get("data", {}).get("list", [])],
                "channelInfo": {
                    "id": "hunhepan",
                    "name": "混合盘",
                    "index": 1004,
                    "channelLogo": ""
                },
                "id": "hunhepan_search",
                "index": 1004
            }

        except Exception as e:
            print(f"混合盘API请求失败: {str(e)}")
            return []