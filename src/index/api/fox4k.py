from ..base import BaseSearch
import requests
import re
from bs4 import BeautifulSoup
import concurrent.futures
import random
import time
import logging
from urllib.parse import urljoin, urlparse
from requests.adapters import HTTPAdapter

# 常量定义
BASE_URL = "https://4kfox.com"
SEARCH_URL = BASE_URL + "/search/%s-------------.html"
SEARCH_PAGE_URL = BASE_URL + "/search/%s----------%d---.html"
DETAIL_URL = BASE_URL + "/video/%s.html"
DEFAULT_TIMEOUT = 15  # 默认超时时间 - 增加超时时间避免网络慢的问题
DEFAULT_HTTP_PROXY = "http://154.219.110.34:51422"
DEFAULT_SOCKS5_PROXY = "socks5://154.219.110.34:51423"
DEBUG_MODE = False  # 调试开关 - 默认关闭
PROXY_ENABLED = False  # 代理开关 - 默认关闭
MAX_CONCURRENCY = 50  # 并发数限制 - 大幅提高并发数
MAX_PAGES = 10  # 最大分页数（避免无限请求）

# 预编译正则表达式
DETAIL_ID_REGEX = re.compile(r'/video/(\d+)\.html')
MAGNET_LINK_REGEX = re.compile(r'magnet:\?xt=urn:btih:[0-9a-fA-F]{40}[^"\'\s]*')
ED2K_LINK_REGEX = re.compile(r'ed2k://\|file\|[^|]+\|[^|]+\|[^|]+\|/?')
YEAR_REGEX = re.compile(r'(\d{4})')
PAN_LINK_REGEXES = {
    "baidu": re.compile(r'https?://pan\.baidu\.com/s/[0-9a-zA-Z_-]+(?:\?pwd=[0-9a-zA-Z]+)?(?:&v=\d+)?'),
    "aliyun": re.compile(r'https?://(?:www\.)?alipan\.com/s/[0-9a-zA-Z_-]+'),
    "tianyi": re.compile(r'https?://cloud\.189\.cn/t/[0-9a-zA-Z_-]+(?:\([^)]*\))?'),
    "uc": re.compile(r'https?://drive\.uc\.cn/s/[0-9a-fA-F]+(?:\?[^"\s]*)?'),
    "mobile": re.compile(r'https?://caiyun\.139\.com/[^"\s]+'),
    "115": re.compile(r'https?://115\.com/s/[0-9a-zA-Z_-]+'),
    "pikpak": re.compile(r'https?://mypikpak\.com/s/[0-9a-zA-Z_-]+'),
    "xunlei": re.compile(r'https?://pan\.xunlei\.com/s/[0-9a-zA-Z_-]+(?:\?pwd=[0-9a-zA-Z]+)?'),
    "123": re.compile(r'https?://(?:www\.)?123pan\.com/s/[0-9a-zA-Z_-]+'),
    "quark": re.compile(r'https?://pan\.quark\.cn/s/[0-9a-fA-F]+(?:\?pwd=[0-9a-zA-Z]+)?'),
}
QUARK_LINK_REGEX = re.compile(r'https?://pan\.quark\.cn/s/[0-9a-fA-F]+(?:\?pwd=[0-9a-zA-Z]+)?')
PASSWORD_REGEXES = [
    re.compile(r'\?pwd=([0-9a-zA-Z]+)'),  # URL中的pwd参数
    re.compile(r'提取码[：:]\s*([0-9a-zA-Z]+)'),  # 提取码：xxxx
    re.compile(r'访问码[：:]\s*([0-9a-zA-Z]+)'),  # 访问码：xxxx
    re.compile(r'密码[：:]\s*([0-9a-zA-Z]+)'),  # 密码：xxxx
    re.compile(r'（访问码[：:]\s*([0-9a-zA-Z]+)）'),  # （访问码：xxxx）
]

# 性能统计（原子操作）
search_requests = 0
detail_page_requests = 0
cache_hits = 0
cache_misses = 0
total_search_time = 0  # 纳秒
total_detail_time = 0  # 纳秒

class Fox4kSearch(BaseSearch):
    def __init__(self):
        self.optimized_client = self.create_optimized_http_client()

    def create_proxy_transport(self, proxy_url):
        transport = {
            'max_idle_conns': 200,
            'max_idle_conns_per_host': 50,
            'max_conns_per_host': 100,
            'idle_conn_timeout': 90,
            'disable_keep_alives': False,
            'disable_compression': False,
            'write_buffer_size': 16 * 1024,
            'read_buffer_size': 16 * 1024,
        }

        if not proxy_url:
            return transport

        if proxy_url.startswith("socks5://"):
            # SOCKS5代理
            transport['proxy'] = {'http': proxy_url, 'https': proxy_url}
            if DEBUG_MODE:
                logging.debug(f"🔧 [Fox4k DEBUG] 使用SOCKS5代理: {proxy_url}")
        else:
            # HTTP代理
            transport['proxy'] = {'http': proxy_url, 'https': proxy_url}
            if DEBUG_MODE:
                logging.debug(f"🔧 [Fox4k DEBUG] 使用HTTP代理: {proxy_url}")

        return transport

    def create_optimized_http_client(self):
        selected_proxy = ""

        if PROXY_ENABLED:
            # 随机选择代理类型
            proxy_types = ["", DEFAULT_HTTP_PROXY, DEFAULT_SOCKS5_PROXY]
            selected_proxy = random.choice(proxy_types)
        else:
            # 代理未启用，使用直连
            selected_proxy = ""
            if DEBUG_MODE:
                logging.debug("🔧 [Fox4k DEBUG] 代理功能已禁用，使用直连模式")

        transport = self.create_proxy_transport(selected_proxy)
        if not transport:
            transport = self.create_proxy_transport("")

        if not selected_proxy and PROXY_ENABLED:
            logging.debug("🔧 [Fox4k DEBUG] 使用直连模式")
        session = requests.Session()
                # 配置适配器，增加连接池大小
        adapter = HTTPAdapter(
            pool_connections=20,  # 连接池中的连接数
            pool_maxsize=50,      # 连接池最大连接数
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def search(self, keyword):
        result, err = self.search_with_result(keyword)
        if err:
            return None
        return result

    def search_with_result(self, keyword):
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] SearchWithResult 开始 - keyword: {keyword}")

        result, err = self.async_search_with_result(keyword, self.search_impl)
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] SearchWithResult 完成 - 结果数: {len(result['results'])}, 错误: {err}")
        if result['results']:
            logging.debug("🔧 [Fox4k DEBUG] 前3个结果示例:")
            for i, r in enumerate(result['results']):
                if i >= 3:
                    break
                logging.debug(f"  {i+1}. 标题: {r['title']}, 链接数: {len(r['links'])}")

        # 转换为标准格式
        standard_results = []
        for item in result['results']:
            # 转换链接格式
            cloud_links = []
            for link in item['links']:
                cloud_link = {
                    "link": link['url'] + (f"?pwd={link['password']}" if link['password'] else ""),
                    "cloudType": link['type']
                }
                cloud_links.append(cloud_link)

            standard_item = {
                "messageId": item['unique_id'],
                "title": item['title'],
                "pubDate": "2022-11-03T14:07:54+00:00",  # 使用固定时间
                "content": item['content'],
                "image": "",  # 暂时为空，可以考虑从item中提取图片URL
                "cloudLinks": cloud_links,
                "tags": item['tags'],
                "magnetLink": "",  # 暂时为空
                "channel": "4K影视",
                "channelId": "fox4k"
            }
            standard_results.append(standard_item)

        return {
            "list": standard_results,
            "channelInfo": {
                "id": "fox4k",
                "name": "4K影视",
                "index": 1000,
                "channelLogo": ""
            },
            "id": "fox4k",
            "index": 1000
        }, None

    def search_impl(self, keyword):
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] searchImpl 开始执行 - keyword: {keyword}")
        start_time = time.time()
        global search_requests
        search_requests += 1

        encoded_keyword = requests.utils.quote(keyword)
        all_results = []

        # 1. 搜索第一页，获取总页数
        first_page_results, total_pages, err = self.search_page(encoded_keyword, 1)
        if err:
            return None, err
        all_results.extend(first_page_results)

        # 2. 如果有多页，继续搜索其他页面（限制最大页数）
        max_pages_to_search = total_pages
        if max_pages_to_search > MAX_PAGES:
            max_pages_to_search = MAX_PAGES

        if total_pages > 1 and max_pages_to_search > 1:
            # 并发搜索其他页面
            results = [None] * (max_pages_to_search - 1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
                futures = {executor.submit(self.search_page, encoded_keyword, page): page for page in range(2, max_pages_to_search + 1)}
                for future in concurrent.futures.as_completed(futures):
                    page = futures[future]
                    page_results, _, err = future.result()
                    if not err:
                        all_results.extend(page_results)

        # 3. 并发获取详情页信息
        all_results = self.enrich_with_detail_info(all_results)

        # 4. 过滤关键词匹配的结果
        results = self.filter_results_by_keyword(all_results, keyword)

        # 记录性能统计
        search_duration = time.time() - start_time
        global total_search_time
        total_search_time += search_duration

        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] searchImpl 完成 - 原始结果: {len(all_results)}, 过滤后结果: {len(results)}, 耗时: {search_duration}秒")

        return results, None

    def search_page(self, encoded_keyword, page):
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] searchPage 开始 - 第{page}页, keyword: {encoded_keyword}")

        # 1. 构建搜索URL
        search_url = SEARCH_URL % encoded_keyword if page == 1 else SEARCH_PAGE_URL % (encoded_keyword, page)

        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] 构建的URL: {search_url}")

        # 2. 创建带超时的上下文
        start_time = time.time()

        # 3. 创建请求
        headers = {
            "User-Agent": self.get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Referer": BASE_URL + "/",
            "X-Forwarded-For": self.generate_random_ip(),
            "X-Real-IP": self.generate_random_ip(),
            "sec-ch-ua-platform": "macOS",
        }

        if DEBUG_MODE:
            logging.debug("🔧 [Fox4k DEBUG] 使用随机UA: %s", headers["User-Agent"])
            logging.debug("🔧 [Fox4k DEBUG] 使用随机IP: %s", headers["X-Forwarded-For"])

        # 5. 发送HTTP请求
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] 开始发送HTTP请求到: {search_url}")
            logging.debug("🔧 [Fox4k DEBUG] 请求头信息:")
            for key, value in headers.items():
                logging.debug(f"    {key}: {value}")

        resp, err = self.do_request_with_retry(search_url, headers)
        if err:
            return None, 0, err

        # 6. 检查状态码
        if resp.status_code != 200:
            if DEBUG_MODE:
                logging.debug(f"❌ [Fox4k DEBUG] 状态码异常: {resp.status_code}")
            return None, 0, f"第{page}页请求返回状态码: {resp.status_code}"

        # 7. 读取并打印HTML响应
        html_content = resp.text
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] 第{page}页 HTML长度: {len(html_content)} bytes")

        # 保存HTML到文件（仅在调试模式下）
        if DEBUG_MODE:
            html_dir = "./html"
            import os
            os.makedirs(html_dir, exist_ok=True)
            filename = f"fox4k_page_{page}_{encoded_keyword.replace('%', '_')}.html"
            filepath = os.path.join(html_dir, filename)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logging.debug(f"✅ [Fox4k DEBUG] HTML已保存到: {filepath}")
            except Exception as e:
                logging.debug(f"❌ [Fox4k DEBUG] 保存HTML文件失败: {e}")

        # 解析HTML响应
        doc = BeautifulSoup(html_content, 'html.parser')

        # 8. 解析分页信息
        total_pages = self.parse_total_pages(doc)

        # 9. 提取搜索结果
        results = []
        for item in doc.select('.hl-list-item'):
            result = self.parse_search_result_item(item)
            if result:
                results.append(result)
        return results, total_pages, None

    def parse_total_pages(self, doc):
        # 查找分页信息，格式为 "1 / 2"
        page_info = doc.select_one('.hl-page-tips a')
        if not page_info:
            return 1
        page_info_text = page_info.get_text(strip=True)
        if not page_info_text:
            return 1

        # 解析 "1 / 2" 格式
        parts = page_info_text.split('/')
        if len(parts) != 2:
            return 1

        total_pages_str = parts[1].strip()
        try:
            total_pages = int(total_pages_str)
            if total_pages < 1:
                return 1
            return total_pages
        except ValueError:
            return 1

    def parse_search_result_item(self, item):
        # 获取详情页链接
        link_element = item.select_one('.hl-item-pic a')
        if not link_element:
            return None
        href = link_element.get('href')
        if not href:
            return None

        # 补全URL
        if href.startswith('/'):
            href = urljoin(BASE_URL, href)

        # 提取ID
        matches = DETAIL_ID_REGEX.search(href)
        if not matches or len(matches.groups()) < 1:
            return None
        id = matches.group(1)

        # 获取标题
        title_element = item.select_one('.hl-item-title a')
        if not title_element:
            return None
        title = title_element.get_text(strip=True)
        if not title:
            return None

        # 获取封面图片
        img_element = item.select_one('.hl-item-thumb')
        image_url = img_element.get('data-original', '') if img_element else ''
        if image_url and image_url.startswith('/'):
            image_url = urljoin(BASE_URL, image_url)

        # 获取资源状态
        status = item.select_one('.hl-pic-text .remarks')
        status_text = status.get_text(strip=True) if status else ''

        # 获取评分
        score = item.select_one('.hl-text-conch.score')
        score_text = score.get_text(strip=True) if score else ''

        # 获取基本信息（年份、地区、类型）
        basic_info_elements = item.select('.hl-item-sub')
        basic_info = basic_info_elements[0].get_text(strip=True) if basic_info_elements else ''

        # 获取简介
        description = basic_info_elements[-1].get_text(strip=True) if basic_info_elements else ''

        # 解析年份、地区、类型
        year, region, category = "", "", ""
        if basic_info:
            parts = basic_info.split('·')
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if score_text in part:
                    continue
                if not year and YEAR_REGEX.match(part):
                    year = part
                elif not region:
                    region = part
                elif not category:
                    category = part
                else:
                    category += " " + part

        # 构建标签
        tags = []
        if status_text:
            tags.append(status_text)
        if year:
            tags.append(year)
        if region:
            tags.append(region)
        if category:
            tags.append(category)

        # 构建内容描述
        content = description
        if basic_info:
            content = basic_info + "\n" + description
        if score_text:
            content = "评分: " + score_text + "\n" + content

        return {
            "unique_id": f"fox4k-{id}",
            "title": title,
            "content": content,
            "datetime": None,  # 使用零值而不是None，参考jikepan插件标准
            "tags": tags,
            "links": [],  # 初始为空，后续在详情页中填充
            "channel": "",  # 插件搜索结果，Channel必须为空
        }

    def enrich_with_detail_info(self, results):
        if not results:
            return results

        # 使用信号量控制并发数
        semaphore = [True] * MAX_CONCURRENCY
        enriched_results = results.copy()

        def fetch_detail(index):
            nonlocal semaphore
            # 获取详情页信息
            detail_info = self.get_detail_info(enriched_results[index]['unique_id'].split('-')[1])
            if detail_info:
                enriched_results[index]['links'] = detail_info['downloads']
                if detail_info['content']:
                    enriched_results[index]['content'] = detail_info['content']
                # 补充标签
                for tag in detail_info['tags']:
                    if tag not in enriched_results[index]['tags']:
                        enriched_results[index]['tags'].append(tag)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
            futures = [executor.submit(fetch_detail, i) for i in range(len(enriched_results))]
            concurrent.futures.wait(futures)

        # 过滤掉没有有效下载链接的结果
        valid_results = [result for result in enriched_results if result['links']]
        return valid_results

    def get_detail_info(self, id):
        if DEBUG_MODE:
            logging.debug(f"🔧 [Fox4k DEBUG] getDetailInfo 开始 - ID: {id}")
        start_time = time.time()
        global detail_page_requests
        detail_page_requests += 1

        # 构建详情页URL
        detail_url = DETAIL_URL % id

        # 创建带超时的上下文
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Referer": BASE_URL + "/",
        }

        # 发送请求
        resp, err = self.do_request_with_retry(detail_url, headers)
        if err:
            return None

        # 解析HTML
        doc = BeautifulSoup(resp.text, 'html.parser')

        # 解析详情页信息
        detail = {
            'downloads': [],
            'tags': [],
            'timestamp': time.time(),
        }

        # 获取标题
        title_element = doc.select_one('h2.hl-dc-title')
        detail['title'] = title_element.get_text(strip=True) if title_element else ''

        # 获取封面图片
        img_element = doc.select_one('.hl-dc-pic .hl-item-thumb')
        if img_element and 'data-original' in img_element.attrs:
            image_url = img_element['data-original']
            if image_url.startswith('/'):
                image_url = urljoin(BASE_URL, image_url)
            detail['image_url'] = image_url

        # 获取剧情简介
        content_element = doc.select_one('.hl-content-wrap .hl-content-text')
        detail['content'] = content_element.get_text(strip=True) if content_element else ''

        # 提取详细信息作为标签
        for li in doc.select('.hl-vod-data ul li'):
            text = li.get_text(strip=True)
            if text:
                # 清理标签文本
                text = text.replace("：", ": ")
                if "类型:" in text or "地区:" in text or "语言:" in text:
                    detail['tags'].append(text)

        # 提取下载链接
        self.extract_download_links(doc, detail)

        # 记录性能统计
        detail_duration = time.time() - start_time
        global total_detail_time
        total_detail_time += detail_duration

        return detail

    def extract_download_links(self, doc, detail):
        # 提取页面中所有文本内容，寻找链接
        page_text = doc.get_text()

        for pan_type, regex in PAN_LINK_REGEXES.items():
            matches = regex.findall(page_text)
            for pan_link in matches:
                # 提取密码（如果有）
                password = self.extract_password_from_text(page_text, pan_link)
                self.add_download_link(detail, pan_type, pan_link, password)

        # 4. 在特定的下载区域查找链接
        for downlist_section in doc.select(".hl-rb-downlist"):
            # 获取质量版本信息
            current_quality = ""
            for tab_btn in downlist_section.select(".hl-tabs-btn"):
                if "active" in tab_btn.get("class", []):
                    current_quality = tab_btn.get_text(strip=True)

            # 提取各种下载链接
            for link_item in downlist_section.select(".hl-downs-list li"):
                item_text = link_item.get_text()
                item_html = str(link_item)

                # 从 data-clipboard-text 属性提取链接
                clipboard_text = link_item.select_one(".down-copy")
                if clipboard_text and "data-clipboard-text" in clipboard_text.attrs:
                    self.process_found_link(detail, clipboard_text["data-clipboard-text"], current_quality)

                # 从 href 属性提取链接
                for link in link_item.select("a"):
                    if "href" in link.attrs:
                        self.process_found_link(detail, link["href"], current_quality)

                # 从文本内容中提取链接
                self.extract_links_from_text(detail, item_text, current_quality)
                self.extract_links_from_text(detail, item_html, current_quality)

        # 5. 在播放源区域也查找链接
        for playlist_section in doc.select(".hl-rb-playlist"):
            section_text = playlist_section.get_text()
            section_html = str(playlist_section)
            self.extract_links_from_text(detail, section_text, "播放源")
            self.extract_links_from_text(detail, section_html, "播放源")

    def process_found_link(self, detail, link, quality):
        if not link:
            return

        # 检查网盘链接
        for pan_type, regex in PAN_LINK_REGEXES.items():
            if regex.match(link):
                password = self.extract_password_from_link(link)
                self.add_download_link(detail, pan_type, link, password)
                return

    def extract_links_from_text(self, detail, text, quality):
        # 网盘链接
        for pan_type, regex in PAN_LINK_REGEXES.items():
            matches = regex.findall(text)
            for pan_link in matches:
                password = self.extract_password_from_text(text, pan_link)
                self.add_download_link(detail, pan_type, pan_link, password)

    def extract_password_from_link(self, link):
        # 首先检查URL参数中的密码
        for regex in PASSWORD_REGEXES:
            matches = regex.search(link)
            if matches and len(matches.groups()) > 0:
                return matches.group(1)
        return ""

    def extract_password_from_text(self, text, link):
        # 首先从链接本身提取密码
        password = self.extract_password_from_link(link)
        if password:
            return password

        # 然后从周围文本中查找密码
        for regex in PASSWORD_REGEXES:
            matches = regex.search(text)
            if matches and len(matches.groups()) > 0:
                return matches.group(1)

        return ""

    def add_download_link(self, detail, link_type, link_url, password):
        if not link_url:
            return

        # 检查是否已存在
        for existing_link in detail['downloads']:
            if existing_link['url'] == link_url:
                return

        # 创建链接对象
        link = {
            "type": link_type,
            "url": link_url,
            "password": password,
        }

        detail['downloads'].append(link)

    def do_request_with_retry(self, url, headers):
        max_retries = 3
        last_err = None

        if DEBUG_MODE:
            logging.debug(f"🔄 [Fox4k DEBUG] 开始重试机制 - 最大重试次数: {max_retries}")

        for i in range(max_retries):
            if DEBUG_MODE:
                logging.debug(f"🔄 [Fox4k DEBUG] 第 {i+1}/{max_retries} 次尝试")

            if i > 0:
                # 指数退避重试
                backoff = (2 ** (i - 1)) * 0.2  # 0.2, 0.4, 0.8 seconds
                if DEBUG_MODE:
                    logging.debug(f"⏳ [Fox4k DEBUG] 等待 {backoff} 秒后重试")
                time.sleep(backoff)

            try:
                attempt_start = time.time()
                resp = self.optimized_client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
                attempt_duration = time.time() - attempt_start

                if DEBUG_MODE:
                    logging.debug(f"🔧 [Fox4k DEBUG] 第 {i+1} 次尝试耗时: {attempt_duration}秒")

                if resp.status_code == 200:
                    if DEBUG_MODE:
                        logging.debug(f"✅ [Fox4k DEBUG] 第 {i+1} 次尝试成功!")
                    return resp, None

                if DEBUG_MODE:
                    logging.debug(f"❌ [Fox4k DEBUG] 第 {i+1} 次尝试状态码异常: {resp.status_code}")

                # 读取响应体以便调试
                if resp.text and len(resp.text) > 0:
                    body_preview = resp.text
                    if len(body_preview) > 200:
                        body_preview = body_preview[:200] + "..."
                    if DEBUG_MODE:
                        logging.debug(f"🔧 [Fox4k DEBUG] 响应体预览: {body_preview}")

                last_err = f"状态码 {resp.status_code}"
            except Exception as e:
                if DEBUG_MODE:
                    logging.debug(f"❌ [Fox4k DEBUG] 第 {i+1} 次尝试失败: {e}")
                last_err = e
                continue

        if DEBUG_MODE:
            logging.debug("❌ [Fox4k DEBUG] 所有重试都失败了!")
        return None, f"重试 {max_retries} 次后仍然失败: {last_err}"


    def filter_results_by_keyword(self, results, keyword):
        # 简单的关键词过滤
        filtered_results = []
        for result in results:
            if keyword.lower() in result['title'].lower() or keyword.lower() in result['content'].lower():
                filtered_results.append(result)
        return filtered_results

    def async_search_with_result(self, keyword, search_func, *args):
        # 简单的异步搜索实现
        try:
            results, err = search_func(keyword)
            return {"results": results or [], "is_final": True}, err
        except Exception as e:
            return {"results": [], "is_final": True}, str(e)