from ..base import BaseSearch
import requests
from typing import List, Dict, Any
import time
import re
from bs4 import BeautifulSoup
import hashlib
import urllib.parse

class XiaotusoSearch(BaseSearch):
    """小兔搜资源搜索实现"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self._sign_key_cache = {}

    def _get_sign_key(self, keyword: str) -> str:
        """
        动态获取 NEXT_PUBLIC_SIGN_KEY，按 keyword 缓存
        """
        if keyword in self._sign_key_cache:
            return self._sign_key_cache[keyword]
        q = urllib.parse.quote(keyword)
        url = f"https://xiaotusoso.com/sopan?q={q}"
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'referer': url,
            'priority': 'u=0, i',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
        }
        cookies = {
            '_ga': 'GA1.1.908594567.1753181907',
            '_ga_XF5VQM9RJN': 'GS2.1.s1754393631$o2$g1$t1754394468$j58$l0$h0'
        }
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        script_tag = None
        for s in soup.find_all("script", src=True):
            if "/_next/static/chunks/app/" in s["src"] and "sopan/page-" in s["src"]:
                script_tag = s
                break
        if not script_tag:
            raise Exception("未找到目标script标签")
        script_url = "https://xiaotusoso.com" + script_tag["src"]
        script_resp = requests.get(script_url, headers=headers, cookies=cookies, timeout=10)
        # 提取 runtimeEnv 结构体
        m_env = re.search(r'runtimeEnv\s*:\s*\{([^}]+)\}', script_resp.text)
        if not m_env:
            raise Exception("未找到 runtimeEnv 结构体")
        env_block = m_env.group(1)
        m_key = re.search(r'NEXT_PUBLIC_SIGN_KEY["\']?\s*:\s*["\']([^"\']+)["\']', env_block)
        if not m_key:
            raise Exception("未找到 NEXT_PUBLIC_SIGN_KEY")
        sign_key = m_key.group(1)
        self._sign_key_cache[keyword] = sign_key
        return sign_key

    def _build_sign_string_sha256(self, e: dict, s: str, t: str) -> str:
        """
        按 key 排序，将 e 转为 key=value&key2=value2...，再拼接 &timestamp=s&app_key=t，最后返回其 SHA256 十六进制字符串
        """
        a = "&".join(f"{k}={e[k]}" for k in sorted(e.keys()))
        l = f"{a}&timestamp={s}&app_key={t}"
        return hashlib.sha256(l.encode("utf-8")).hexdigest()

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索小兔搜资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        return self._search_with_api(keyword)

    def _search_with_api(self, keyword: str) -> List[Dict[str, Any]]:
        """通过API搜索"""
        url = "https://xiaotusoso.com/api/extra/disk/search"
        payload = {
            "page": 1,
            "size": 20,
            "q": keyword,
            "type": "ALL",
            "share_time": "ALL",
            "format": "",
            "mode": "common",
            "gateway": "G1"
        }
        # 动态获取 sign key
        sign_key = self._get_sign_key(keyword)
        # 生成 x-timestamp
        x_timestamp = str(int(time.time() * 1000))
        # 用 build_sign_string_sha256 算法生成 x-sign
        x_sign = self._build_sign_string_sha256(payload, x_timestamp, sign_key)
        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://xiaotusoso.com',
            'priority': 'u=1, i',
            'referer': f'https://xiaotusoso.com/sopan?q={urllib.parse.quote(keyword)}',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'x-sign': x_sign,
            'x-timestamp': x_timestamp,
        }
        cookies = {
            '_ga': 'GA1.1.908594567.1753181907',
            '_ga_XF5VQM9RJN': 'GS2.1.s1754393631$o2$g1$t1754394255$j18$l0$h0'
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # 资源列表在 result['list']
            items = data.get('result', {}).get('list', [])
            def safe_tags(tags):
                return tags if isinstance(tags, list) else []
            def build_link(item):
                link = item.get("link", "")
                disk_pass = item.get("disk_pass", "")
                if disk_pass:
                    # 百度盘等需拼接提取码
                    if "baidu.com" in link and "pwd=" not in link:
                        return f"{link}?pwd={disk_pass}"
                return link

            return {
                "list": [{
                    "messageId": str(item.get("disk_id", "")),
                    "title": self._clean_html(item.get("disk_name", "")),
                    "pubDate": item.get("shared_time", ""),
                    "content": self._clean_html(item.get("disk_name", "")),
                    "image": "",
                    "cloudLinks": [{
                        "link": build_link(item),
                        "cloudType": self.detect_cloud_type(item.get("link", ""))
                    }],
                    "tags": safe_tags(item.get("tags", [])),
                    "magnetLink": "",
                    "channel": "小兔搜",
                    "channelId": "xiaotuso"
                } for item in items],
                "channelInfo": {
                    "id": "xiaotuso",
                    "name": "小兔搜",
                    "index": 1002,
                    "channelLogo": ""
                },
                "id": "xiaotuso",
                "index": 1002
            }

        except Exception as e:
            print(f"小兔搜 API请求失败: {str(e)}")
            return []