from ..base import BaseSearch
import requests
from typing import List, Dict, Any

class MelostSearch(BaseSearch):
    """Melost 资源搜索实现"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索 Melost 资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        return self._search_with_api(keyword)

    def _search_with_api(self, keyword: str) -> List[Dict[str, Any]]:
        """通过API搜索"""
        url = "https://www.melost.cn/v1/search/disk"
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://www.melost.cn',
            'priority': 'u=1, i',
            'referer': 'https://www.melost.cn/search?q=%E7%91%9E%E5%A5%87%E5%AE%9D%E5%AE%9D',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'x-path': '/v1/search/disk',
            'x-request-id': '8335',
            'x-sign': '9b44197c904df876ef45356ef4bd0bd2',
            'x-time': '1754393646339',
        }
        cookies = {
            'is_dark': 'false',
            'UM_distinctid': '1987a01db4663b-0b17f1b54d35ab8-17525636-16a7f0-1987a01db47965',
            'CNZZDATA1281420470': '490495754-1754393599-%7C1754393646'
        }
        payload = {
            "page": 1,
            "q": keyword,
            "user": "",
            "exact": False,
            "format": [],
            "share_time": "",
            "size": 15,
            "order": "",
            "type": "",
            "search_ticket": "",
            "exclude_user": [],
            "adv_params": {
                "wechat_pwd": "",
                "platform": "pc",
                "fp_data": "46610e3a37100d16691e838ce69bfc1c"
            }
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # 资源列表在 data['list']
            items = data.get('data', {}).get('list', [])
            def safe_tags(tags):
                return tags if isinstance(tags, list) else []
            return {
                "list": [{
                    "messageId": str(item.get("disk_id", "")),
                    "title": self._clean_html(item.get("disk_name", "")),
                    "pubDate": item.get("shared_time", ""),
                    "content": self._clean_html(item.get("disk_name", "")),
                    "image": "",
                    "cloudLinks": [{
                        "link": item.get("link", ""),
                        "cloudType": self.detect_cloud_type(item.get("link", ""))
                    }],
                    "tags": safe_tags(item.get("tags", [])),
                    "magnetLink": "",
                    "channel": "Melost",
                    "channelId": "melost"
                } for item in items],
                "channelInfo": {
                    "id": "melost",
                    "name": "Melost",
                    "index": 1001,
                    "channelLogo": ""
                },
                "id": "melost",
                "index": 1001
            }

        except Exception as e:
            print(f"Melost API请求失败: {str(e)}")
            return []