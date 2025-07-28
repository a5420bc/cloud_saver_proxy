from ..base import BaseSearch
import requests
from typing import Dict, Any
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import re

class XzysSearch(BaseSearch):
    """xzys.fun 网盘搜索实现（主列表页+详情页并发解析，参考rrdynb/roubuyaoqian）"""

    def __init__(self):
        self.base_url = "https://xzys.fun/search.html"
        self.headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'cache-control': 'max-age=0',
            'priority': 'u=0, i',
            'referer': 'https://xzys.fun/article/p/272/27238.html',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        }
        self.cookies = {
            '_ga': 'GA1.1.1971061124.1753356849',
            '_ga_ZCQ89Y79QC': 'GS2.1.s1753419887$o4$g1$t1753419899$j48$l0$h352426529'
        }

    def search(self, keyword: str, pagesize: int = 20) -> Dict[str, Any]:
        """
        搜索xzys.fun资源并返回结构化结果，真实网盘链接需并发请求详情页
        """

        try:
            params = {
                "keyword": keyword
            }
            resp = requests.get(
                self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                params=params,
                timeout=10
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 解析所有资源条目
            list_boxes = soup.select('div.list-boxes')
            detail_items = []
            for box in list_boxes:
                try:
                    # 标题
                    a_title = box.select_one('a.text_title_p')
                    if not a_title:
                        continue
                    detail_href = a_title['href']
                    detail_url = urllib.parse.urljoin(self.base_url, detail_href)
                    title = self._clean_html(a_title.text)
                    # 图片
                    img = box.select_one('div.left_ly img')
                    image = ""
                    if img and img.has_attr('src'):
                        image = img['src']
                    # 简介
                    p_desc = box.select_one('p.text_p')
                    content = self._clean_html(p_desc.text) if p_desc else title
                    # 时间
                    date_span = box.select_one('div.list-actions span')
                    pub_date = date_span.text.strip().split()[0] if date_span else ""
                    # 组装
                    detail_items.append({
                        "detail_url": detail_url,
                        "detail_href": detail_href,
                        "title": title,
                        "content": content,
                        "pub_date": pub_date,
                        "image": image
                    })
                except Exception as e:
                    print(f"主列表项解析失败: {str(e)}")
                    continue

            # 并发处理详情页，提取真实网盘链接
            def fetch_real_links(detail_url):
                try:
                    detail_headers = {
                        'accept': self.headers['accept'],
                        'accept-language': self.headers['accept-language'],
                        'cache-control': 'max-age=0',
                        'referer': self.base_url,
                        'sec-ch-ua': self.headers['sec-ch-ua'],
                        'sec-ch-ua-mobile': self.headers['sec-ch-ua-mobile'],
                        'sec-ch-ua-platform': self.headers['sec-ch-ua-platform'],
                        'sec-fetch-dest': 'document',
                        'sec-fetch-mode': 'navigate',
                        'sec-fetch-site': 'same-origin',
                        'sec-fetch-user': '?1',
                        'upgrade-insecure-requests': '1',
                        'user-agent': self.headers['user-agent'],
                        'priority': 'u=0, i',
                    }
                    detail_resp = requests.get(
                        detail_url,
                        headers=detail_headers,
                        cookies=self.cookies,
                        timeout=10
                    )
                    detail_resp.raise_for_status()
                    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                    # 网盘链接提取（基类通用方法）
                    return self._extract_cloud_links_from_html(detail_soup)
                except Exception as e:
                    print(f"详情页解析失败: {detail_url} [{type(e).__name__}] {str(e)}")
                    return []

            # 并发获取所有真实链接（用基类方法，max_workers=10）
            real_links_list = self._batch_fetch_details(
                [item["detail_url"] for item in detail_items],
                fetch_real_links,
                max_workers=10
            )

            # 组装最终结果
            results = []
            for idx, item in enumerate(detail_items):
                cloud_links = real_links_list[idx] if idx < len(real_links_list) else []
                if not cloud_links:
                    continue
                results.append({
                    "messageId": item["detail_href"].split('/')[-1].replace('.html', ''),
                    "title": self._clean_html(item["title"]),
                    "pubDate": item["pub_date"],
                    "content": self._clean_html(item["content"]),
                    "image": item["image"],
                    "cloudLinks": cloud_links,
                    "tags": [],
                    "magnetLink": "",
                    "channel": "xzys",
                    "channelId": "xzys"
                })

            return {
                "list": results,
                "channelInfo": {
                    "id": "xzys",
                    "name": "小资源搜",
                    "index": 1016,
                    "channelLogo": ""
                },
                "id": "xzys",
                "index": 1016,
                "total": len(results),
                "keyword": keyword
            }
        except Exception as e:
            print(f"xzys搜索失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "xzys",
                    "name": "小资源搜",
                    "index": 1016,
                    "channelLogo": ""
                },
                "id": "xzys",
                "index": 1016
            }