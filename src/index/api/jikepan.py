from ..base import BaseSearch
import requests
from typing import List, Dict, Any

class JikepanSearch(BaseSearch):
    """����������ʵ��"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self.api_url = "https://api.jikepan.xyz/search"
        self.headers = {
            "Content-Type": "application/json",
            "referer": "https://jikepan.xyz/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def search(self, keyword: str, is_all: bool = False) -> Dict[str, Any]:
        """
        ������������Դ�����ؽṹ�����

        Args:
            keyword: �����ؼ���
            is_all: �Ƿ�ȫ������������Լ10�룩

        Returns:
            ��׼���Ľ���ֵ�
        """
        return self._search_with_api(keyword, is_all)

    def _search_with_api(self, keyword: str, is_all: bool = False) -> Dict[str, Any]:
        payload = {
            "name": keyword,
            "is_all": is_all
        }
        try:
            resp = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("msg") != "success":
                print(f"API����ʧ��: {data.get('msg')}")
                return {
                    "list": [],
                    "channelInfo": {
                        "id": "jikepan",
                        "name": "������",
                        "index": 1020,
                        "channelLogo": ""
                    },
                    "id": "jikepan",
                    "index": 1020
                }

            results = []
            for idx, item in enumerate(data.get("list", [])):
                links = []
                for link in item.get("links", []):
                    # �����û�����������ͼ�⣬��ⲻ������ԭserviceӳ��
                    link_type = self.detect_cloud_type(link.get("link", ""))
                    if not link_type or link_type == "others":
                        fallback_type = self._convert_link_type(link.get("service", ""))
                        # ���⴦��other����
                        if fallback_type == "others" and "drive.uc.cn" in link.get("link", "").lower():
                            fallback_type = "uc"
                        if fallback_type:
                            link_type = fallback_type
                    if not link_type:
                        continue
                    links.append({
                        "link": link.get("link", ""),
                        "cloudType": link_type,
                        "Password": link.get("pwd", "")
                    })
                if not links:
                    continue
                results.append({
                    "messageId": f"jikepan-{idx}",
                    "title": item.get("name", ""),
                    "pubDate": "",
                    "content": item.get("name", ""),
                    "image": "",
                    "cloudLinks": links,
                    "tags": [],
                    "magnetLink": "",
                    "channel": "������",
                    "channelId": "jikepan"
                })

            return {
                "list": results,
                "channelInfo": {
                    "id": "jikepan",
                    "name": "������",
                    "index": 1020,
                    "channelLogo": ""
                },
                "id": "jikepan",
                "index": 1020
            }
        except Exception as e:
            print(f"API�����쳣: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "jikepan",
                    "name": "������",
                    "index": 1020,
                    "channelLogo": ""
                },
                "id": "jikepan",
                "index": 1020
            }

    def _convert_link_type(self, service: str) -> str:
        service = (service or "").lower()
        mapping = {
            "baidu": "baidu",
            "aliyun": "aliyun",
            "xunlei": "xunlei",
            "quark": "quark",
            "189cloud": "tianyi",
            "115": "115",
            "123": "123",
            "weiyun": "weiyun",
            "pikpak": "pikpak",
            "lanzou": "lanzou",
            "jianguoyun": "jianguoyun",
            "caiyun": "mobile",
            "chengtong": "chengtong",
            "ed2k": "ed2k",
            "magnet": "magnet",
            "unknown": ""
        }
        return mapping.get(service, "others")