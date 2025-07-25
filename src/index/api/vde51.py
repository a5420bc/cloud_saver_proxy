from ..base import BaseSearch
import requests
import re
from typing import List, Dict, Any

class Vde51Search(BaseSearch):
    """
    51vde/太穹乐盘网盘搜索实现，可扩展多站点
    site: "51vde" 或 "taiqiongle"
    """
    def __init__(self, use_playwright: bool = False, site: str = "51vde"):
        self.use_playwright = use_playwright
        # 站点配置
        site_cfg = {
            "51vde": {
                "base_url": "https://51vde.com/api/discussions",
                "headers": {
                    'accept': '*/*',
                    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                    'cache-control': 'no-cache',
                    'pragma': 'no-cache',
                    'priority': 'u=1, i',
                    'referer': 'https://51vde.com/',
                    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"',
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                    'x-csrf-token': 'RvwUaWMJCmP7W0coeHtdAchKNJzfEpihHIGIYBXs'
                },
                "cookies": None
            },
            "taiqiongle": {
                "base_url": "https://www.taiqiongle.com/api/discussions",
                "headers": {
                    'accept': '*/*',
                    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                    'priority': 'u=1, i',
                    'referer': 'https://www.taiqiongle.com/?q=%E6%89%AB%E6%AF%92%E9%A3%8E%E6%9A%B4%20',
                    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"',
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                    'x-csrf-token': 'IwMQuX3UdFLi91gWVBfWdwAmx9ETQou26qk1lTaA'
                },
                "cookies": {
                    "flarum_session": "WM7cSH2jhAKkGmhotGbR1Jvi4vkLnIIjLTfl8B9Y",
                    "_ga": "GA1.1.295149817.1753356828",
                    "_ga_BC2CBCSF5X": "GS2.1.s1753356827$o1$g1$t1753357994$j50$l0$h0"
                }
            }
        }
        if site not in site_cfg:
            raise ValueError(f"不支持的site: {site}")
        self.site = site
        self.base_url = site_cfg[site]["base_url"]
        self.headers = site_cfg[site]["headers"]
        self.cookies = site_cfg[site]["cookies"]

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索51vde资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        try:
            params = {
                "filter[q]": keyword,
                "page[limit]": 3,
                "include": "mostRelevantPost"
            }
            response = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            valid_results = []
            for item in data.get('data', []):
                post = next(
                    (p for p in data.get('included', []) 
                     if p.get('type') == 'posts' and p.get('id') == item.get('relationships', {}).get('mostRelevantPost', {}).get('data', {}).get('id')),
                    None
                )
                if not post:
                    continue
                
                result = self._process_post(item, post)
                if result:
                    valid_results.append(result)
            
            return {
                "list": valid_results,
                "channelInfo": {
                    "id": "51vde",
                    "name": "51vde",
                    "index": 1006,
                    "channelLogo": ""
                },
                "id": "51vde",
                "index": 1006
            }
            
        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return []
    
    def _process_post(self, discussion, post):
        """处理帖子内容"""
        try:
            content = post.get('attributes', {}).get('contentHtml', '')
            
            # 使用正则提取链接
            url_pattern = r'href="(https?://[^"]+)"'
            matches = re.findall(url_pattern, content)
            links = []
            
            for url in matches:
                cloud_type = self.detect_cloud_type(url)
                if cloud_type:
                    links.append({
                        "link": url,
                        "cloudType": cloud_type
                    })
            
            if not links:
                return None
                
            return {
                "messageId": discussion.get('id'),
                "title": discussion.get('attributes', {}).get('title', ''),
                "pubDate": discussion.get('attributes', {}).get('createdAt', ''),
                "content": content.replace('<p>', '').replace('</p>', ''),
                "image": "",
                "cloudLinks": links,
                "tags": [],
                "magnetLink": "",
                "channel": "51vde",
                "channelId": "51vde"
            }
        except Exception as e:
            print(f"帖子处理失败: {str(e)}")
            return None