from ..base import BaseSearch
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
import re
import json

class QuarksoSearch(BaseSearch):
    """
    quark.so 网页搜索实现，解析主列表页 HTML，提取 image, tags, link, title, content, pubDate
    并自动跟进详情页面包屑最后的真实 doc_id 链接，提取 NUXT_DATA JSON，并支持 cookie_id、url 路径索引解析
    """

    def __init__(self):
        self.base_url = "https://www.quark.so/s"
        self.headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'referer': 'https://www.quark.so/',
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

    def search(self, keyword: str) -> Dict[str, Any]:
        """
        解析主列表页 HTML，提取 image, tags, link, title, content, pubDate
        并自动跟进详情页面包屑最后的真实 doc_id 链接，提取 NUXT_DATA JSON
        并解析 cookie_id、url
        """
        try:
            params = {"query": keyword}
            resp = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                timeout=15
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            result_div = soup.find('div', class_='yp-search-result yp-quarkso')
            if not result_div:
                return self._format_results([], keyword)
            items = result_div.find_all('div', class_='yp-search-result-item')
            def fetch_func(item):
                try:
                    # link
                    a_tag = item.find(
                        'a', class_='flex flex-grow overflow-hidden justify-between yp-quarkso')
                    if not a_tag or not a_tag.has_attr('href'):
                        a_tag = item.find('a', class_='yp-quarkso')
                    fake_link = a_tag['href'] if a_tag and a_tag.has_attr(
                        'href') else ""
                    # image
                    img_tag = item.find(
                        'img', class_='object-cover w-full h-full yp-quarkso')
                    image = img_tag['src'] if img_tag and img_tag.has_attr(
                        'src') else ""
                    # title
                    h2 = item.find(
                        'h2', class_='yp-search-result-item-text-title yp-quarkso')
                    title = self._clean_html(h2.text) if h2 else ""
                    # content
                    desc_div = item.find(
                        'div', class_='yp-search-result-item-text-desc yp-quarkso')
                    content = self._clean_html(
                        desc_div.text) if desc_div else ""
                    # pubDate
                    pub_date = ""
                    time_tag = item.find('div', class_='yz-time yp-quarkso')
                    if time_tag:
                        span = time_tag.find('span', class_='yp-quarkso')
                        if span:
                            pub_date = span.text.strip()
                    # tags
                    tags = []
                    tag_list_div = item.find(
                        'div', class_='yz-tag_list yp-quarkso')
                    if tag_list_div:
                        tag_links = tag_list_div.find_all(
                            'a', class_='res_tags-tag_item')
                        tags = [self._clean_html(tag.text)
                                for tag in tag_links]
                    # 跟进详情页，获取真实 doc_id 链接和 NUXT_DATA
                    doc_id, nuxt_json = self._get_real_detail_link_and_nuxtdata(
                        fake_link)
                    # 解析 cookie_id 和真实资源 url
                    cookie_id = self._resolve_cookie_id_chain(nuxt_json)
                    url = self._resolve_resource_url(nuxt_json)
                    ret = self.save_quarkso_resource(url, cookie_id, doc_id)
                    if isinstance(ret, dict) and 'data' in ret and 'final_share_url' in ret['data']:
                        real_link = ret['data']['final_share_url']
                    else:
                        real_link = ""
                    # 返回与 yunso.py 一致的结构
                    return {
                        "messageId": str(doc_id) if doc_id else "",
                        "title": title,
                        "pubDate": pub_date,
                        "content": content,
                        "image": image,
                        "cloudLinks": [{
                            "link": real_link,
                            "cloudType": self.detect_cloud_type(real_link)
                        }],
                        "tags": tags,
                        "magnetLink": "",
                        "channel": "夸克搜",
                        "channelId": "quarkso"
                    }
                except Exception as e:
                    print(f"解析条目失败: {str(e)}")
                    return None

            # 用父类多线程工具并发处理详情页
            results = self._batch_fetch_details(items, fetch_func, max_workers=8)
            # 过滤掉None
            results = [r for r in results if r]
            return self._format_results(results, keyword)
        except Exception as e:
            print(f"quarkso搜索失败: {str(e)}")
            return self._format_results([], keyword)

    def save_quarkso_resource(self, url, cookie_id, doc_id):
        """
        向 https://www.quark.so/v1/local_resource_save 发起POST请求，保存资源。
        """
        try:
            resp = requests.post(
                "https://www.quark.so/v1/local_resource_save",
                headers={
                    "accept": "application/json",
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
                    "cache-control": "no-cache",
                    "content-type": "application/json",
                    "origin": "https://www.quark.so",
                    "pragma": "no-cache",
                    "priority": "u=1, i",
                    "referer": "https://www.quark.so/d/huo-ying-ren-zhe",
                    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "site-id": "default",
                    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
                },
                data=json.dumps({
                    "url": url,
                    "cookie_id": cookie_id,
                    "doc_id": doc_id,
                    "filter_words": []
                })
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            pass

    def _get_real_detail_link_and_nuxtdata(self, fake_link: str):
        """
        跟进详情页，获取面包屑最后的真实 doc_id 链接、doc_id，并提取 NUXT_DATA JSON
        """
        if not fake_link or not fake_link.startswith("http"):
            return "", "", None
        try:
            resp = requests.get(fake_link, headers=self.headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            breadcrumb = soup.find(
                'ul', class_='yp-detail-main-breadcrumb yp-quarkso')
            if not breadcrumb:
                return fake_link, "", None
            all_li = breadcrumb.find_all(
                'li', class_='yp-detail-main-breadcrumb-item yp-quarkso')
            if not all_li:
                return fake_link, "", None
            last_a = all_li[-1].find('a', class_='yp-quarkso')
            if not last_a or not last_a.has_attr('href'):
                return fake_link, "", None
            real_link = last_a['href']
            # 提取 doc_id
            doc_id = ""
            m = re.search(r'/d/([a-zA-Z0-9]+)', real_link)
            if m:
                doc_id = m.group(1)
            # 提取 NUXT_DATA
            script_tag = soup.find("script", {"id": "__NUXT_DATA__"})
            nuxt_json = None
            if script_tag:
                try:
                    nuxt_json = json.loads(script_tag.string)
                except Exception as e:
                    print(f"详情页 NUXT_DATA 解析失败: {str(e)}")
            return doc_id, nuxt_json
        except Exception as e:
            print(f"详情页解析失败: {str(e)}")
            return fake_link, "", None

    # _resolve_json_chain 已移至父类

    def _resolve_cookie_id_chain(self, nuxt_json):
        """
        cookie_id 路径链路:
        261 --> 258 cookie --> 252 [list] --> 251.list --> 213.transfer_save_config --> 212.global_config --> 733 --> 727.resource --> 712.page_config --> 711 --> 710
        --> 708.websiteConfig --> 707.website_config --> pina
        规则：从最后往最前依次取值，遇到list类型取第一个元素，遇到key直接取key，遇到idx则用上一步的结果作为下标
        """
        chain = [
            ("idx", 1),
            ("key", "pinia"),
            ("origin", None),
            ("key", "website_config"),
            ("origin", None),
            ("key", "websiteConfig"),
            ("origin", None),
            ("idx", 1),
            ("origin", None),
            ("idx", 1),
            ("origin", None),
            ("key", "page_config"),
            ("origin", None),
            ("key", "resource"),
            ("origin", None),
            ("idx", 1),
            ("origin", None),
            ("key", "global_config"),
            ("origin", None),
            ("key", "transfer_save_config"),
            ("origin", None),
            ("key", "list"),
            ("origin", None),
            ("list", 1),
            ("origin", None),
            ("key", "cookie"),
            ("origin", None),
        ]
        return self._resolve_json_chain(nuxt_json, chain, match_func=None, nuxt_json=nuxt_json)

    def _resolve_resource_url(self, nuxt_json):
        """
        url 路径: 3.{"is_cache":1,"seo_title":"..."} --> 找到key包含seo_title的dict，取其值，再依次 406.target_url
        """
        chain = [
            ("idx", 2),
            ("match", "seo_title"),
            ("origin", None),
            ("key", "detail_info"),
            ("origin", None),
            ("key", "target_urls"),
            ("origin", None),
            ("list", 0),
            ("origin", None),
            ("key", "target_url"),
            ("origin", None),
        ]
        def match_func(data, val):
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and val in k:
                        return v
            return None
        return self._resolve_json_chain(nuxt_json, chain, match_func=match_func, nuxt_json=nuxt_json)

    def _clean_html(self, html: str) -> str:
        tags = [
            "<em>", "</em>", "<b>", "</b>", "<strong>", "</strong>",
            "<i>", "</i>", "<u>", "</u>", "<br>", "<br/>", "<br />"
        ]
        result = html or ""
        for tag in tags:
            result = result.replace(tag, "")
        result = re.sub(r'<[^>]+>', '', result)
        return result.strip()

    def _format_results(self, results: List[Dict[str, Any]], keyword: str) -> Dict[str, Any]:
        return {
            "list": results,
            "channelInfo": {
                "id": "quarkso",
                "name": "夸克搜",
                "index": 1022,
                "channelLogo": ""
            },
            "id": "quarkso",
            "index": 1022,
            "total": len(results),
            "keyword": keyword
        }