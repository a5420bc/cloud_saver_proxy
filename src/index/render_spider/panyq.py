import asyncio
import random
import time
import traceback
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import os
from typing import List, Dict, Any
from ..base import BaseSearch


class PanyqSearch(BaseSearch):
    """盘易搜爬虫实现"""

    def __init__(self, use_playwright: bool = True):
        self.use_playwright = use_playwright
        self.user_data_dir = os.path.expanduser("~/chrome_profile")
        self._playwright = None
        self.browser = None
        self.popup_semaphore = asyncio.Semaphore(1)  # 控制弹窗并发为1

    async def _async_init(self):
        """异步初始化浏览器实例"""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ],
            ignore_default_args=["--enable-automation"],
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
        )

    async def _get_real_link(self, page, element) -> str:
        """获取跳转后的真实链接"""
        try:
            # 在元素上点击
            link = await element.query_selector('a')
            if link:
                # 点击链接(会在新标签页打开)，使用semaphore控制并发
                async with self.popup_semaphore:
                    async with page.expect_popup() as popup_info:
                        await link.click()

                    # 获取新标签页
                new_page = await popup_info.value

                # 等待更长时间确保跳转完成
                await new_page.wait_for_load_state('networkidle', timeout=10000)
                await asyncio.sleep(2)  # 额外等待2秒

                real_url = new_page.url

                # 关闭新标签页
                return real_url
            return ""
        except Exception as e:
            print(
                f"获取真实链接失败(行号:{traceback.extract_tb(e.__traceback__)[-1].lineno}): {str(e)}")
            return ""
        finally:
            if new_page:
                await new_page.close()


    async def search(self, keyword: str) -> List[Dict[str, Any]]:
        """实现BaseSearch接口"""
        if not self.use_playwright:
            return []

        # 等待浏览器初始化完成
        if not self.browser:
            await self._async_init()
            stealth = Stealth(init_scripts_only=True)
            await stealth.apply_stealth_async(self.browser)

        try:
            page = await self.browser.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            # 执行搜索逻辑
            await page.goto("https://panyq.com/", wait_until="networkidle", timeout=60000)

            try:
                quark_btn = await page.wait_for_selector(
                    'label[for="cat-quark"]',
                    timeout=3000
                )
                await quark_btn.click()
            except:
                pass

            search_box = await page.wait_for_selector(
                'input[name="query"]',
                state="attached",
                timeout=5000
            )
            await search_box.fill("")
            await search_box.type(keyword, delay=50)
            await asyncio.sleep(0.1)
            await search_box.press("Enter")

            await page.wait_for_selector(
                'div.w-full.netdisk',
                state="attached",
                timeout=10000
            )

            # 解析结果
            elements = await page.query_selector_all('div.w-full.border-gray-200.dark\\:text-gray-200.dark\\:border-gray-600.border.p-4.rounded.shadow.overflow-hidden.relative.bg-white.dark\\:bg-gray-700')

            async def process_element(element):
                try:
                    # 提取标题和描述(从netdisk div的span)
                    title = ""
                    description = ""
                    netdisk_div = await element.query_selector('.w-full.netdisk')
                    if netdisk_div:
                        span = await netdisk_div.query_selector('span')
                        if span:
                            # 获取完整文本并按<br>分割
                            full_text = await span.inner_text()
                            parts = [p.strip() for p in full_text.split('\n') if p.strip()]
                            if parts:
                                title = parts[0]  # 第一个非空部分作为标题
                                if len(parts) > 1:
                                    description = ' '.join(parts[1:])  # 剩余部分作为描述

                    # 提取链接
                    a_element = await element.query_selector('a')
                    if not a_element:
                        return None
                    link = await a_element.get_attribute('href')
                    if not link:
                        return None
                    if link.startswith('/'):
                        link = f"https://panyq.com{link}"

                    # 提取图片URL
                    image_url = ""
                    float_div = await element.query_selector('.float-left')
                    if float_div:
                        img_element = await float_div.query_selector('img')
                        if img_element:
                            image_url = await img_element.get_attribute('src')

                    # 获取真实链接
                    real_link = await self._get_real_link(page, element)
                    if not real_link or not real_link.startswith("https://pan.quark.cn/s/"):
                        return None

                    return {
                        "messageId": str(hash(real_link)),
                        "title": title,
                        "pubDate": "",
                        "content": description if description else title,
                        "image": image_url,
                        "cloudLinks": [{"link": real_link, "cloudType": "quark"}],
                        "tags": [],
                        "magnetLink": "",
                        "channel": "盘易搜",
                        "channelId": "panyq"
                    }
                except Exception as e:
                    print(f"解析元素失败: {str(e)}")
                    return None

            # 并发处理所有元素
            tasks = [process_element(element) for element in elements]
            results = await asyncio.gather(*tasks)
            results = [r for r in results if r is not None]  # 过滤掉None结果

            await page.close()

            return {
                "list": results,
                "channelInfo": {
                    "id": "panyq",
                    "name": "盘易搜",
                    "index": 1001,
                    "channelLogo": ""
                },
                "id": "panyq",
                "index": 1001
            }

        except Exception as e:
            print(f"搜索失败: {str(e)}")
            print(
                f"获取真实链接失败(行号:{traceback.extract_tb(e.__traceback__)[-1].lineno}): {str(e)}")
            print(traceback.format_exc())
            return []
