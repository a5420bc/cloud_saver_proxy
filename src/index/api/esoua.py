from ..base import BaseSearch
import requests
import json
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

class EsouaSearch(BaseSearch):
    """e搜啊网盘搜索实现"""
    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self.base_url = "https://www.esoua.com/search"
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://www.esoua.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.esoua.com/search?q=%E6%89%AB%E9%BB%91%E9%A3%8E%E6%9A%B4',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索e搜啊资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        return self._search_with_html(keyword)
    def _search_with_html(self, keyword: str) -> List[Dict[str, Any]]:
        """通过HTML页面搜索"""
        try:
            params = {"q": keyword}
            response = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 准备并发任务
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for item in soup.select('div.search-item'):
                    title = item.select_one('a[title] span').get_text(strip=True)
                    link = "https://www.esoua.com" + item.select_one('a[title]')['href']
                    
                    # 提取网盘类型和日期
                    meta_items = item.select('div.search-item-icon')
                    cloud_type = meta_items[1].get_text(strip=True)
                    date = meta_items[2].get_text(strip=True)
                    
                    futures.append(executor.submit(
                        self._process_detail_page,
                        link, title, cloud_type, date
                    ))
                
                # 获取并发结果
                valid_results = []
                for future in futures:
                    try:
                        result = future.result()
                        if result:
                            valid_results.append(result)
                    except Exception as e:
                        print(f"详情页处理异常: {str(e)}")
            
            return {
                "list": valid_results,
                "channelInfo": {
                    "id": "esoua",
                    "name": "爱搜",
                    "index": 1005,
                    "channelLogo": ""
                },
                "id": "esoua",
                "index": 1005
            }
            
        except Exception as e:
            print(f"HTML请求失败: {str(e)}")
            return []
    
    def _process_detail_page(self, link, title, cloud_type, date):
        """处理详情页(多线程调用)"""
        try:
            detail_resp = requests.get(link, headers=self.headers, timeout=10)
            detail_resp.raise_for_status()
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            # 提取用户指定的资源链接
            resource_link = detail_soup.select_one('span.semi-typography.resource-link a')
            if not resource_link:
                return None
                
            # 验证链接有效性
            resp = requests.head(resource_link['href'], timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                return {
                    "messageId": link.split('/')[-1],
                    "title": title,
                    "pubDate": date,
                    "content": "",
                    "image": "",
                    "cloudLinks": [{
                        "link": resource_link['href'],
                        "cloudType": self._map_cloud_type(cloud_type)
                    }],
                    "tags": [],
                    "magnetLink": "",
                    "channel": "爱搜",
                    "channelId": "esoua"
                }
        except Exception as e:
            print(f"详情页处理失败: {str(e)}")
            return None

    def _map_cloud_type(self, disk_type: str) -> str:
        """将原始disk_type映射为标准云盘类型
        
        Args:
            disk_type: 原始disk_type值
            
        Returns:
            标准化的云盘类型标识
        """
        mapping = {
            "QUARK": "quark",
            "ALY": "aliyun"
        }
        return mapping.get(disk_type.upper(), disk_type.lower())