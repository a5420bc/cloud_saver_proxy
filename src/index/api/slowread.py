from ..base import BaseSearch
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
import urllib.parse
import re

class SlowreadSearch(BaseSearch):
    """
    so.slowread.net 网页搜索实现，解析搜索结果页面提取资源信息
    """

    def __init__(self):
        self.base_url = "https://so.slowread.net/search"
        self.headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://so.slowread.net',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'referer': 'https://so.slowread.net/search',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': self.get_random_ua(),
            'x-forwarded-for': self.generate_random_ip()
        }
        self.cookies = {
            '_ga': 'GA1.1.367266693.1755743033',
            'adblock_message_closed': 'true',
            '_ga_49NY1DKNZV': 'GS2.1.s1755743033$o1$g1$t1755744366$j60$l0$h0',
            '_ga_RH4LQRSZV5': 'GS2.1.s1755743171$o1$g1$t1755746433$j40$l0$h0'
        }

    def search(self, keyword: str) -> Dict[str, Any]:
        """
        搜索so.slowread.net资源并返回结构化结果
        """
        try:
            # 构造POST数据
            data = {
                'pan_type': '',
                'query': keyword
            }
            
            # 发送POST请求
            resp = requests.post(
                self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                data=data,
                timeout=15
            )
            resp.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 查找结果容器
            results_section = soup.find('section', class_='results-section')
            if not results_section:
                return self._format_results([], keyword)
                
            # 查找所有结果卡片
            result_cards = results_section.find_all('div', class_='result-card')
            
            results = []
            for card in result_cards:
                try:
                    # 提取图标信息（用于确定网盘类型）
                    icon_img = card.find('img', class_='result-icon')
                    icon_alt = icon_img.get('alt', '').lower() if icon_img else ''
                    
                    # 提取链接和标题
                    link_tag = card.find('a', class_='result-link')
                    if not link_tag:
                        continue
                        
                    link = link_tag.get('href', '')
                    title = link_tag.get_text(strip=True)
                    
                    if not link or not title:
                        continue
                    
                    # 根据图标确定网盘类型
                    cloud_type = self.detect_cloud_type(link)
                    
                    # 构造结果对象
                    result = {
                        "messageId": self._extract_message_id(link),
                        "title": self._clean_html(title),
                        "pubDate": "",
                        "content": self._clean_html(title),
                        "image": "",
                        "cloudLinks": [{
                            "link": link,
                            "cloudType": cloud_type
                        }],
                        "tags": [icon_alt] if icon_alt else [],
                        "magnetLink": "",
                        "channel": "SlowRead",
                        "channelId": "slowread"
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"解析结果项失败: {str(e)}")
                    continue
            
            return self._format_results(results, keyword)
            
        except Exception as e:
            print(f"slowread搜索失败: {str(e)}")
            return self._format_results([], keyword)

    def _extract_message_id(self, link: str) -> str:
        """
        从链接中提取唯一标识符
        """
        # 尝试从链接中提取ID
        match = re.search(r'/s/([a-zA-Z0-9]+)', link)
        if match:
            return match.group(1)
        return link


    def _format_results(self, results: List[Dict[str, Any]], keyword: str) -> Dict[str, Any]:
        """
        格式化结果，与quarkso.py保持一致
        """
        return {
            "list": results,
            "channelInfo": {
                "id": "slowread",
                "name": "SlowRead",
                "index": 1070,
                "channelLogo": ""
            },
            "id": "slowread",
            "index": 1070,
            "total": len(results),
            "keyword": keyword
        }