import re
import requests
from typing import List, Dict, Any
from ..base import BaseSearch

class PansearchSearch(BaseSearch):
    """pansearch.me 网盘搜索实现"""

    def __init__(self):
        self.website_url = "https://www.pansearch.me/search"
        self.api_url_template = "https://www.pansearch.me/_next/data/{buildId}/search.json"
        self.headers = {
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'referer': 'https://www.pansearch.me/',
            'connection': 'keep-alive',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
        }

    # 云盘类型识别统一用父类方法

    def _get_build_id(self) -> str:
        """从首页HTML提取buildId"""
        resp = requests.get(self.website_url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        html = resp.text
        # 先用正则提取 "buildId":"xxxx"
        m = re.search(r'"buildId":"([^"]+)"', html)
        if m:
            return m.group(1)
        # 兼容 __NEXT_DATA__ 脚本
        m2 = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if m2:
            import json
            try:
                data = json.loads(m2.group(1))
                if "buildId" in data:
                    return data["buildId"]
            except Exception:
                pass
        raise Exception("未能提取 buildId")

    def _extract_link_and_pwd(self, content: str) -> Dict[str, str]:
        """从内容中提取链接和密码"""
        # 提取 href="..." 链接
        link = ""
        pwd = ""
        m = re.search(r'href="([^"]+)"', content)
        if m:
            link = m.group(1)
        # 提取 ?pwd=xxxx
        m2 = re.search(r'\?pwd=([a-zA-Z0-9]+)', content)
        if m2:
            pwd = m2.group(1)
        return {"link": link, "pwd": pwd}

    def _extract_title(self, content: str, keyword: str) -> str:
        """从内容中提取标题"""
        # 标题通常在"名称："之后
        m = re.search(r'名称：([^\n<]+)', content)
        if m:
            return self._clean_html(m.group(1))
        return keyword

    def _clean_html(self, html: str) -> str:
        """简单清理HTML标签"""
        # 替换常见标签
        html = re.sub(r"<span class='highlight-keyword'>|</span>|<a [^>]+>|</a>|<br>|<p>|</p>", "", html)
        # 去除所有剩余标签
        html = re.sub(r'<[^>]+>', '', html)
        return html.strip()

    def search(self, keyword: str, page: int = 1) -> Dict[str, Any]:
        """
        搜索pansearch资源并返回结构化结果
        Args:
            keyword: 搜索关键词
            page: 页码（pansearch.me 只支持offset，不支持page，这里page=1时offset=0, page=2时offset=10）
        Returns:
            标准化的结果字典
        """
        try:
            build_id = self._get_build_id()
            api_url = self.api_url_template.format(buildId=build_id)
            offset = (page - 1) * 10
            params = {
                "keyword": keyword,
                "offset": offset
            }
            resp = requests.get(api_url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("pageProps", {}).get("data", {}).get("data", [])
            total = data.get("pageProps", {}).get("data", {}).get("total", len(items))
            list_data = []
            for item in items:
                content = item.get("content", "")
                link_info = self._extract_link_and_pwd(content)
                link = link_info["link"]
                pwd = link_info["pwd"]
                list_data.append({
                    "messageId": f"pansearch-{item.get('id', '')}",
                    "title": self._extract_title(content, keyword),
                    "pubDate": item.get("time", ""),
                    "content": content,
                    "fileType": "dir",
                    "uploader": "",
                    "cloudLinks": [{
                        "link": link,
                        "cloudType": self.detect_cloud_type(link),
                        "pwd": pwd
                    }],
                    "tags": [],
                    "magnetLink": "",
                    "channel": "pansearch",
                    "channelId": "pansearch"
                })
            return {
                "list": list_data,
                "channelInfo": {
                    "id": "pansearch",
                    "name": "pansearch",
                    "index": 1011,
                    "channelLogo": ""
                },
                "id": "pansearch",
                "index": 1011,
                "total": total,
                "keyword": keyword
            }
        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "pansearch",
                    "name": "pansearch",
                    "index": 1011,
                    "channelLogo": ""
                },
                "id": "pansearch",
                "index": 1011
            }