from ..base import BaseSearch
import requests
from typing import Dict, Any
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import re

class RrdynbSearch(BaseSearch):
    """rrdynb.com 网盘搜索实现（详情页并发解析，严格参考roubuyaoqian.py）"""

    def __init__(self):
        self.base_url = "https://www.rrdynb.com/plus/search.php"
        self.domain = "https://www.rrdynb.com"
        self.headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'priority': 'u=0, i',
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
            'PHPSESSID': 'p34rcbmg7qp8h20mperrd46b56',
            'cf_clearance': 'r_sMFg.SZyJxo.XS39HeyN9eov7slUGGcwjnCg2Axs0-1753413048-1.2.1.1-IRtLuqs2yeHxk0WrfGqpr.CHR9apEkvEU6fDzNPJj6Lte4ziPD6eIkNou31zIWHN4myTXCvdoIiv3aH8DFetikjdHDx4rkhfoWncF.QILAuq5fDjHZP8_5_ya.YWyEYVDyR0k5ATZC.zONputD7TbxCbxXcVPphrTSWmCEFtZGyTU6c5bzQh.zEheAuV9MnL1E9Rv9om4zNJSFFkVdwi1Y0sOhhreSlYdtvO7opW3mU'
        }

    def search(self, keyword: str, pagesize: int = 50) -> Dict[str, Any]:
        """
        搜索rrdynb资源并返回结构化结果，真实网盘链接需并发请求详情页
        """

        def extract_pub_date(tags_text):
            # 匹配第一个 yyyy-mm-dd
            m = re.search(r'\d{4}-\d{2}-\d{2}', tags_text)
            return m.group(0) if m else ""

        try:
            params = {
                "q": keyword,
                "pagesize": pagesize,
                "submit": ""
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
            movielist = soup.select('ul#movielist li.pure-g')
            # 预处理所有详情页链接和主信息
            detail_items = []
            for li in movielist:
                try:
                    a_thumb = li.select_one('a.movie-thumbnails')
                    a_title = li.select_one('div.intro h2 a')
                    if not a_thumb or not a_title:
                        continue
                    detail_href = a_thumb['href'] if a_thumb.has_attr('href') else a_title['href']
                    detail_url = urllib.parse.urljoin(self.base_url, detail_href)
                    title = self._clean_html(a_title.get('title', '').strip() or a_title.text.strip())
                    brief = li.select_one('div.brief')
                    content = self._clean_html(brief.text) if brief else title
                    tags_div = li.select_one('div.tags')
                    tags_text = tags_div.text if tags_div else ""
                    pub_date = extract_pub_date(tags_text)
                    img = a_thumb.select_one('img')
                    image = ""
                    if img and img.has_attr('src'):
                        src = img['src']
                        # 只补全以/开头的相对路径，防止重复补全
                        if src.startswith("http"):
                            image = src
                        else:
                            image = urllib.parse.urljoin(self.domain, src)
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
                        'referer': f'https://www.rrdynb.com/plus/search.php?q={urllib.parse.quote(keyword)}',
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
                    "channel": "rrdynb",
                    "channelId": "rrdynb"
                })

            return {
                "list": results,
                "channelInfo": {
                    "id": "rrdynb",
                    "name": "人人电影",
                    "index": 1014,
                    "channelLogo": ""
                },
                "id": "rrdynb",
                "index": 1014,
                "total": len(results),
                "keyword": keyword
            }
        except Exception as e:
            print(f"rrdynb搜索失败: {str(e)}")
            return {
                "list": [],
                "channelInfo": {
                    "id": "rrdynb",
                    "name": "人人电影",
                    "index": 1015,
                    "channelLogo": ""
                },
                "id": "rrdynb",
                "index": 1015
            }