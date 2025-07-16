from ..base import BaseSearch
import requests
import re
from typing import List, Dict, Any
import urllib.parse

class AipanSearch(BaseSearch):
    """爱盘搜索实现"""

    def __init__(self, source_id: int = 2, use_playwright: bool = False):
        """初始化爱盘搜索
        
        Args:
            source_id: 数据源ID (1-8)
            use_playwright: 是否使用playwright
        """
        self.source_id = source_id
        self.use_playwright = use_playwright
        self.base_url = f"https://www.aipan.me/api/sources/{self.source_id}"

    def _clean_title(self, title: str) -> str:
        """清理资源标题，提取第一个有效资源名称"""
        # 如果包含分号，取第一个分号前的内容
        if ';' in title:
            title = title.split(';')[0].strip()
        # 如果包含"1、 "等编号，提取第一个编号后的内容
        if '、' in title:
            parts = [p.strip() for p in title.split('、') if p.strip()]
            if len(parts) > 1 and parts[0][0].isdigit():
                title = parts[1].split(':')[0].strip()
        # 去除多余空格和特殊字符
        title = ' '.join(title.split())
        # 如果处理后为空，返回原始名称
        return title if title else "未命名资源"

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索爱盘资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        return self._search_with_api(keyword)

    def _search_with_api(self, keyword: str) -> List[Dict[str, Any]]:
        """通过API搜索"""
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://www.aipan.me',
            'referer': f'https://www.aipan.me/search?keyword={urllib.parse.quote(keyword)}',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json={"name": keyword},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # 转换为标准格式，只保留天翼和夸克资源
            return {
                "list": [{
                    "messageId": "",
                    "title": self._clean_title(item["name"]),
                    "pubDate": "",
                    "content": self._clean_title(item["name"]),
                    "image": "",
                    "cloudLinks": [{
                        "link": link["link"],
                        "cloudType": "quark" if "quark" in link["link"] else "tianyi",
                        "password": link.get("pwd", "")
                    } for link in item["links"]
                       if "quark" in link["link"] or "189.cn" in link["link"]],
                    "tags": [],
                    "magnetLink": "",
                    "channel": f"爱盘-{self.source_id}",
                    "channelId": f"aipan_{self.source_id}"
                } for item in data.get("list", [])
                   if item.get("links") and
                      any("quark" in link["link"] or "189.cn" in link["link"]
                          for link in item["links"])],
                "channelInfo": {
                    "id": f"aipan_{self.source_id}",
                    "name": f"爱盘-{self.source_id}",
                    "index": 1002,
                    "channelLogo": ""
                },
                "id": f"aipan_{self.source_id}",
                "index": 1002
            }

        except Exception as e:
            print(f"API请求失败: {str(e)}")
            return []