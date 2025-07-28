from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseSearch(ABC):
    """搜索基类，支持多线程调用"""
    
    @abstractmethod
    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """执行搜索并返回格式化结果
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            标准化的结果列表
        """
        pass
    def detect_cloud_type(self, url: str) -> str:
        """根据URL判断云盘类型，所有子类统一调用"""
        if not url:
            return ""
        if 'pan.baidu.com' in url or 'yun.baidu.com' in url:
            return "baiduPan"
        elif 'cloud.189.cn' in url:
            return "tianyi"
        elif 'aliyundrive.com' in url or 'alipan.com' in url:
            return "aliyun"
        elif '115.com' in url or 'anxia.com' in url or '115cdn.com' in url:
            return "pan115"
        elif '123' in url and '.com/s/' in url:
            return "pan123"
        elif 'pan.quark.cn' in url:
            return "quark"
        elif 'caiyun.139.com' in url:
            return "yidong"
        elif 'drive.uc.cn' in url:
            return "uc"
        return ""

    def _clean_html(self, text):
        """通用HTML标签清理"""
        import re
        return re.sub(r'<[^>]+>', '', text or '').strip()

    def _extract_cloud_links_from_html(self, soup):
        """
        从BeautifulSoup对象中提取所有支持的云盘链接
        :param soup: BeautifulSoup对象
        :return: [{'link': url, 'cloudType': type}, ...]
        """
        links = []
        for a in soup.find_all('a', href=True):
            link = a['href']
            cloud_type = self.detect_cloud_type(link)
            if cloud_type:
                links.append({
                    "link": link,
                    "cloudType": cloud_type
                })
        return links

    def _batch_fetch_details(self, detail_items, fetch_func, max_workers=5):
        """
        通用并发详情页处理工具
        :param detail_items: 详情页参数列表（如URL、dict等）
        :param fetch_func: 单个详情页处理函数，参数为detail_items的元素
        :param max_workers: 并发线程数
        :return: 结果列表，顺序与detail_items一致
        """
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(fetch_func, detail_items))
        return results
