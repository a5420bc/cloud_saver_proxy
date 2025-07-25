from ..base import BaseSearch
import requests
from typing import Dict, Any

class AlipanxSearch(BaseSearch):
    """alipanx.com 阿里盘盘侠网盘搜索实现"""
    def __init__(self):
        self.base_url = "https://www.alipanx.com/v1/search/disk"
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://www.alipanx.com',
            'priority': 'u=1, i',
            'referer': 'https://www.alipanx.com/search?q=%E7%91%9E%E5%A5%87%E5%AE%9D%E5%AE%9D',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            # 以下header如需动态生成可后续扩展
            'x-body-sign': 'NmQbMm02FdXnFpX3DZD3MRFoNUrdD2T7DdDnF2PfNUO=',
            'x-path': '/v1/search/disk',
            'x-request-id': '5802',
            'x-sign': 'NRWsMpQnDRrdMZbpDUD4NRPsMUDmMUe1DUQvNpN3FZN=',
            'x-time': '1753409070598'
        }
        self.cookies = {
            'is_dark': 'false'
        }

    def search(self, keyword: str, page: int = 1) -> Dict[str, Any]:
        """
        搜索alipanx资源并返回结构化结果
        Args:
            keyword: 搜索关键词
            page: 页码
        Returns:
            标准化的结果字典
        """
        try:
            payload = {
                "page": page,
                "q": keyword,
                "user": "",
                "exact": False,
                "format": [],
                "share_time": "",
                "size": 15,
                "type": "",
                "exclude_user": [],
                "adv_params": {
                    "wechat_pwd": "",
                    "platform": "pc"
                }
            }
            resp = requests.post(
                self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("data", {}).get("list", [])
            list_data = []
            for item in results:
                # 字段映射与清洗
                def clean_html(text):
                    import re
                    return re.sub(r'<[^>]+>', '', text or '')

                link = item.get("link", "")
                pwd = item.get("disk_pass", "")
                disk_type = item.get("disk_type", "")
                tags = item.get("tags") or []
                list_data.append({
                    "messageId": item.get("doc_id", "") or item.get("disk_id", ""),
                    "title": clean_html(item.get("disk_name", "")),
                    "pubDate": item.get("shared_time", ""),
                    "content": clean_html(item.get("files", "")),
                    "fileType": item.get("disk_type", ""),
                    "uploader": item.get("share_user", ""),
                    "cloudLinks": [{
                        "link": link,
                        "cloudType": self._map_cloud_type(disk_type),
                        "pwd": pwd
                    }],
                    "tags": tags if isinstance(tags, list) else [],
                    "magnetLink": "",
                    "channel": "alipanx",
                    "channelId": "alipanx"
                })
            return {
                "list": list_data,
                "channelInfo": {
                    "id": "alipanx",
                    "name": "阿里盘盘侠",
                    "index": 1012,
                    "channelLogo": ""
                },
                "id": "alipanx",
                "index": 1012,
                "total": data.get("data", {}).get("total", len(results)),
                "keyword": keyword
            }
        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "alipanx",
                    "name": "阿里盘盘侠",
                    "index": 1012,
                    "channelLogo": ""
                },
                "id": "alipanx",
                "index": 1012
            }
        # 云盘类型映射
    def _map_cloud_type(self, disk_type: str) -> str:
        mapping = {
            "QUARK": "quark",
            "ALY": "aliyun"
        }
        return mapping.get((disk_type or "").upper(), (disk_type or "").lower())