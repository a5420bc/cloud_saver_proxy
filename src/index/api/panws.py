from ..base import BaseSearch
import requests
from typing import List, Dict, Any

class PanwsSearch(BaseSearch):
    """panws.top 网盘搜索实现"""
    def __init__(self):
        self.base_url = "https://www.panws.top/api/Api-search"
        self.headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.panws.top/search',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }
        self.cookies = {
            '__51vcke__3JWrr1aVig0T1isI': 'bafb7dab-804c-564a-a11d-fc66a4c1c7a4',
            '__51vuft__3JWrr1aVig0T1isI': '1752849409426',
            '__vtins__3JWrr1aVig0T1isI': '%7B%22sid%22%3A%20%22e29b6bbd-2f11-518d-8183-ca98425d80d5%22%2C%20%22vd%22%3A%201%2C%20%22stt%22%3A%200%2C%20%22dr%22%3A%200%2C%20%22expires%22%3A%201753172171708%2C%20%22ct%22%3A%201753170371708%7D',
            '__51uvsct__3JWrr1aVig0T1isI': '4'
        }

    def _detect_cloud_type(self, url: str) -> str:
        """根据URL检测云盘类型"""
        if not url:
            return ""
        if 'pan.baidu.com' in url or 'yun.baidu.com' in url:
            return "baiduPan"
        elif 'cloud.189.cn' in url:
            return "tianyi"
        elif 'aliyundrive.com' in url or 'alipan.com' in url:
            return "aliyun"
        elif '115.com' in url or 'anxia.com' in url or '115cdn.com' in url:
            return "pan115"
        elif '123' in url and '.com/s/' in url:
            return "pan123"
        elif 'pan.quark.cn' in url:
            return "quark"
        elif 'caiyun.139.com' in url:
            return "yidong"
        elif 'drive.uc.cn' in url:
            return "uc"
        return ""

    def search(self, keyword: str, page: int = 1) -> Dict[str, Any]:
        """
        搜索panws资源并返回结构化结果
        Args:
            keyword: 搜索关键词
            page: 页码
        Returns:
            标准化的结果字典
        """
        try:
            params = {
                "q": keyword,
                "page": page
            }
            resp = requests.get(
                self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                params=params,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            list_data = []
            for item in results:
                link = item.get("link", "")
                list_data.append({
                    "name": item.get("name", ""),
                    "link": link,
                    "category": item.get("category", ""),
                    "cloudType": self.detect_cloud_type(link)
                })
            return {
                "list": list_data,
                "channelInfo": {
                    "id": "panws",
                    "name": "panws",
                    "index": 1010,
                    "channelLogo": ""
                },
                "id": "panws",
                "index": 1010
            }
        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "panws",
                    "name": "panws",
                    "index": 1010,
                    "channelLogo": ""
                },
                "id": "panws",
                "index": 1010
            }