from ..base import BaseSearch
import requests
from typing import Dict, Any

class RoubuyaoqianSearch(BaseSearch):
    """roubuyaoqian.com 网盘搜索实现"""
    def __init__(self):
        self.base_url = "https://roubuyaoqian.com/v1/search/disk"
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://roubuyaoqian.com',
            'priority': 'u=1, i',
            'referer': 'https://roubuyaoqian.com/search?q=%E9%93%81%E8%83%86%E7%81%AB%E8%BD%A6%E4%BE%A0',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'x-body-sign': '4224abf2c174f1d11677b6224f1f87c7',
            'x-path': '/v1/search/disk',
            'x-sign': 'abb66892020ea63c6dcfcb4516b36f5b',
            'x-time': '1753409442095'
        }
        self.cookies = {
            'is_dark': 'false'
        }

    def search(self, keyword: str, page: int = 1) -> Dict[str, Any]:
        """
        搜索roubuyaoqian资源并返回结构化结果，真实网盘链接需二次请求详情页
        """
        from bs4 import BeautifulSoup
        from concurrent.futures import ThreadPoolExecutor

        def clean_html(text):
            import re
            return re.sub(r'<[^>]+>', '', text or '')

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

            # 并发处理详情页，提取真实网盘链接
            def fetch_real_link(doc_id):
                if not doc_id:
                    return ""
                url = f"https://roubuyaoqian.com/doc/{doc_id}"
                try:
                    import urllib.parse
                    detail_headers = {
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                        'cache-control': 'max-age=0',
                        'referer': f'https://roubuyaoqian.com/search?q={urllib.parse.quote(keyword)}',
                        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"macOS"',
                        'sec-fetch-dest': 'document',
                        'sec-fetch-mode': 'navigate',
                        'sec-fetch-site': 'same-origin',
                        'sec-fetch-user': '?1',
                        'upgrade-insecure-requests': '1',
                        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                        'priority': 'u=0, i',
                    }
                    detail_resp = requests.get(url, headers=detail_headers, timeout=10)
                    detail_resp.raise_for_status()
                    soup = BeautifulSoup(detail_resp.text, 'html.parser')
                    # 兼容多种结构，优先找 class 包含 resource-link 的 a 标签
                    link_tag = soup.select_one('span.semi-typography._resource-link_1u20h_158 a')
                    if not link_tag:
                        link_tag = soup.select_one('span.semi-typography.resource-link a')
                    if link_tag and link_tag.has_attr('href'):
                        return link_tag['href']
                except Exception as e:
                    print(f"详情页解析失败: {doc_id} [{type(e).__name__}] {str(e)}")
                return ""

            # 并发获取所有真实链接
            with ThreadPoolExecutor(max_workers=5) as executor:
                doc_ids = [item.get("doc_id", "") for item in results]
                real_links = list(executor.map(fetch_real_link, doc_ids))

            list_data = []
            for idx, item in enumerate(results):
                pwd = item.get("disk_pass", "")
                disk_type = item.get("disk_type", "")
                tags = item.get("tags") or []
                real_link = real_links[idx] if idx < len(real_links) else ""
                list_data.append({
                    "messageId": item.get("doc_id", "") or item.get("disk_id", ""),
                    "title": clean_html(item.get("disk_name", "")),
                    "pubDate": item.get("shared_time", ""),
                    "content": clean_html(item.get("files", "")),
                    "fileType": item.get("disk_type", ""),
                    "uploader": item.get("share_user", ""),
                    "cloudLinks": [{
                        "link": real_link,
                        "cloudType": self._map_cloud_type(disk_type),
                        "pwd": pwd
                    }] if real_link else [],
                    "tags": tags if isinstance(tags, list) else [],
                    "magnetLink": "",
                    "channel": "roubuyaoqian",
                    "channelId": "roubuyaoqian"
                })
            return {
                "list": list_data,
                "channelInfo": {
                    "id": "roubuyaoqian",
                    "name": "肉不咬钱",
                    "index": 1013,
                    "channelLogo": ""
                },
                "id": "roubuyaoqian",
                "index": 1013,
                "total": data.get("data", {}).get("total", len(results)),
                "keyword": keyword
            }
        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "roubuyaoqian",
                    "name": "肉不咬钱",
                    "index": 1013,
                    "channelLogo": ""
                },
                "id": "roubuyaoqian",
                "index": 1013
            }

    def _map_cloud_type(self, disk_type: str) -> str:
        mapping = {
            "QUARK": "quark",
            "ALY": "aliyun"
        }
        return mapping.get((disk_type or "").upper(), (disk_type or "").lower())