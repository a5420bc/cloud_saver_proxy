from ..base import BaseSearch
import requests
from typing import List, Dict, Any

class VcsosoSearch(BaseSearch):
    """vcsoso.com Qsearch接口"""

    def __init__(self):
        self.api_url = "https://vcsoso.com/api/tool/Qsearch"
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "cache-control": "no-cache",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://vcsoso.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        self.cookies = {
            "PHPSESSID": "9b6bc6f87cdbd645a20e402922183683",
            "_clck": "1nvqkgq%7C2%7Cfyd%7C0%7C2049",
            "_clsk": "g3l616%7C1754905704385%7C6%7C1%7Cb.clarity.ms%2Fcollect"
        }

    def search(self, keyword: str) -> Dict[str, Any]:
        """
        搜索vcsoso资源并返回libvio.py格式结构
        """
        try:
            resp = requests.post(
                self.api_url,
                headers=self.headers,
                cookies=self.cookies,
                json={"title": keyword},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            result_list = []
            for item in items:
                url = item.get("url", "")
                result_list.append({
                    "messageId": str(item.get("id", "")),
                    "title": item.get("title", ""),
                    "pubDate": "",
                    "content": item.get("title", ""),
                    "image": "",
                    "cloudLinks": [{
                        "link": url,
                        "cloudType": self.detect_cloud_type(url)
                    }],
                    "tags": [],
                    "magnetLink": "",
                    "channel": "Vcsoso",
                    "channelId": "vcsoso"
                })
            return {
                "list": result_list,
                "channelInfo": {
                    "id": "vcsoso",
                    "name": "Vcsoso",
                    "index": 1060,
                    "channelLogo": ""
                },
                "id": "vcsoso",
                "index": 1060
            }
        except Exception as e:
            print(f"vcsoso Qsearch API请求失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "vcsoso",
                    "name": "Vcsoso",
                    "index": 1060,
                    "channelLogo": ""
                },
                "id": "vcsoso",
                "index": 1060
            }