from ..base import BaseSearch
import requests
import urllib.parse
from typing import List, Dict, Any


class YunsoSearch(BaseSearch):
    """天翼搜搜索实现"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索天翼搜资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        return self._search_with_api(keyword)

    def _search_with_api(self, keyword: str) -> List[Dict[str, Any]]:
        """通过API搜索"""
        base_url = "https://www.yunso.net/api/opensearch.php"
        params = {
            "wd": keyword,
            "uk": "",
            "mode": 90001
        }

        try:
            response = requests.get(
                base_url,
                params=params,
                timeout=10,  # 10秒超时
                headers={'Connection': 'keep-alive'}
            )
            response.raise_for_status()
            data = response.json()

            # 转换为标准格式，只保留夸克盘结果
            return {
                "list": [{
                    "messageId": str(item.get("ScrID", "")),
                    "title": item.get("ScrName", ""),
                    "pubDate": "2022-11-03T14:07:54+00:00",
                    "content": item.get("ScrName", ""),
                    "image": "",
                    "cloudLinks": [{
                        "link": item.get("Scrurl", ""),
                        "cloudType": self.detect_cloud_type(item.get("Scrurl", ""))
                    }],
                    "tags": [
                    ],
                    "magnetLink": "",
                    "channel": "云桥计划",
                    "channelId": "yunso"
                } for item in data.get("Data", []) if item.get("Scrurlname") == "夸克"],
                "channelInfo": {
                    "id": "yunso",
                    "name": "云桥计划",
                    "index": 1000,
                    "channelLogo": ""
                },
                "id": "test",
                "index": 14
            }

        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return []
