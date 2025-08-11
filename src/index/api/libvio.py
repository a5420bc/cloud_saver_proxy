from ..base import BaseSearch
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import urllib.parse
import threading
import re
import json

class LibvioSearch(BaseSearch):
    """Libvio可用域名接口，自动检测并缓存可用域名"""

    _cached_domain = None
    _cache_lock = threading.Lock()

    def __init__(self):
        pass

    def _get_all_domains(self) -> List[str]:
        url = "https://www.libvio.app/all.html"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            domains = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "libvio.app" not in href and "libvio.com" not in href:
                    domains.append(href.rstrip("/"))
            return domains
        except Exception as e:
            print(f"Libvio获取域名失败: {str(e)}")
            return []

    def refresh_cache(self, keyword: str = "测试") -> str:
        domains = self._get_all_domains()
        for domain in domains:
            if self._test_domain(domain, keyword):
                with self._cache_lock:
                    self._cached_domain = domain
                return domain
        with self._cache_lock:
            self._cached_domain = None
        return None

    def _test_domain(self, domain: str, keyword: str) -> bool:
        search_path = f"/search/-------------.html?wd={urllib.parse.quote(keyword)}&submit="
        test_url = domain + search_path
        try:
            resp = requests.get(test_url, timeout=8)
            if resp.status_code == 403:
                return False
            return resp.status_code == 200
        except Exception:
            return False

    def fetch_detail_info(self, domain: str, detail_url: str) -> dict:
        """
        访问详情页，提取海报、标题、简介、年份、cloudLinks（只用js变量player_aaaa.url方案）
        """
        full_url = domain + detail_url if not detail_url.startswith("http") else detail_url
        info = {"poster": "", "title": "", "desc": "", "year": "", "cloudLinks": []}
        try:
            resp = requests.get(full_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # 海报
                thumb = soup.find("div", class_="stui-content__thumb")
                if thumb:
                    img = thumb.find("img")
                    if img:
                        info["poster"] = img.get("data-original") or img.get("src") or ""
                # 标题
                detail = soup.find("div", class_="stui-content__detail")
                if detail:
                    h1 = detail.find("h1", class_="title")
                    if h1:
                        info["title"] = h1.get_text(strip=True)
                    # 简介
                    p_desc = detail.find("p", class_="desc detail")
                    if p_desc:
                        sketch = p_desc.find("span", class_="detail-sketch")
                        content = p_desc.find("span", class_="detail-content")
                        desc = ""
                        if sketch:
                            desc += sketch.get_text(strip=True)
                        if content:
                            desc += content.get_text(strip=True)
                        info["desc"] = desc
                    # 年份（兼容“年份：2025 /上映：”等格式）
                    for p in detail.find_all("p", class_="data"):
                        m = re.search(r"年份：\s*(\d{4})", p.get_text())
                        if m:
                            info["year"] = m.group(1)
                            break
                # cloudLinks: 只用js变量player_aaaa.url方案
                quark_play_urls = []
                for head in soup.find_all("div", class_="stui-vodlist__head"):
                    h3 = head.find("h3")
                    if h3 and "视频下载" in h3.get_text() and "夸克" in h3.get_text():
                        ul = head.find_next("ul", class_="stui-content__playlist clearfix")
                        if ul:
                            for a in ul.find_all("a", href=True):
                                if a["href"].startswith("/play/"):
                                    quark_play_urls.append(domain + a["href"])
                # 依次访问所有播放页，只用js变量player_aaaa.url
                for play_url in quark_play_urls:
                    try:
                        play_resp = requests.get(play_url, timeout=10)
                        if play_resp.status_code == 200:
                            play_html = play_resp.text
                            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', play_html, re.DOTALL)
                            if m:
                                js_obj_str = m.group(1)
                                js_obj = json.loads(js_obj_str)
                                url = js_obj.get("url", "").replace('\\/', '/')
                                if url.startswith("http"):
                                    info["cloudLinks"].append({
                                        "link": url,
                                        "cloudType": self.detect_cloud_type(url)
                                    })
                    except Exception as e:
                        print(f"解析播放页失败: {str(e)}")
        except Exception as e:
            print(f"解析详情页信息失败: {str(e)}")
        return info

    def search(self, keyword: str) -> Dict[str, Any]:
        """
        搜索Libvio可用域名，返回与yunso.py完全一致的结构，批量采集用父类多线程工具
        """
        with self._cache_lock:
            domain = self._cached_domain
        if not domain:
            domain = self.refresh_cache(keyword)
        if not domain:
            return {
                "list": [],
                "channelInfo": {
                    "id": "libvio",
                    "name": "Libvio",
                    "index": 1050,
                    "channelLogo": ""
                },
                "id": "libvio",
                "index": 1050
            }
        # 搜索页
        search_url = f"{domain}/search/-------------.html?wd={urllib.parse.quote(keyword)}&submit="
        detail_links_set = set()
        try:
            resp = requests.get(search_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                ul = soup.find("ul", class_="stui-vodlist clearfix")
                if ul:
                    for li in ul.find_all("li"):
                        a = li.find("a", href=True)
                        if a and re.match(r"^/detail/\d+\.html", a["href"]):
                            detail_links_set.add(a["href"])
        except Exception as e:
            print(f"Libvio搜索页解析失败: {str(e)}")

        detail_links = list(detail_links_set)
        # 多线程批量采集详情页
        detail_infos = super()._batch_fetch_details(
            detail_links,
            lambda u: self.fetch_detail_info(domain, u),
            max_workers=8
        )
        # 组装list
        result_list = []
        for detail_url, info in zip(detail_links, detail_infos):
            if info and info.get("cloudLinks"):
                result_list.append({
                    "messageId": detail_url,
                    "title": info["title"],
                    "pubDate": info["year"],
                    "content": info["desc"],
                    "image": info["poster"],
                    "cloudLinks": info["cloudLinks"],
                    "tags": [],
                    "magnetLink": "",
                    "channel": "Libvio",
                    "channelId": "libvio"
                })

        return {
            "list": result_list,
            "channelInfo": {
                "id": "libvio",
                "name": "Libvio",
                "index": 1050,
                "channelLogo": ""
            },
            "id": "libvio",
            "index": 1050
        }