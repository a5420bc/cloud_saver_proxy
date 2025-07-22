from ..base import BaseSearch
import requests
import re
from typing import List, Dict, Any

class Vde51Search(BaseSearch):
    """51vde网盘搜索实现"""
    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self.base_url = "https://51vde.com/api/discussions"
        self.headers = {
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
        }

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
                timeout=10
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

    def _detect_cloud_type(self, url: str) -> str:
        """根据URL检测云盘类型
        
        Args:
            url: 资源链接
            
        Returns:
            标准化的云盘类型标识
        """
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
        return ""