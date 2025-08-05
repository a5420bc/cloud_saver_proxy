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

    def _batch_fetch_details(self, tasks, func, max_workers=8):
        """
        通用线程池批量处理工具
        """
        import concurrent.futures
        results = [None] * len(tasks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {executor.submit(func, task): i for i, task in enumerate(tasks)}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    results[idx] = result
                except Exception as e:
                    print(f"batch_fetch_details error: {str(e)}")
        return [r for r in results if r]

    def _resolve_json_chain(self, data, chain, match_func=None, nuxt_json=None):
        """
        通用链式 JSON 路径解析工具
        :param data: 初始 JSON 数据
        :param chain: 操作链 [("key"/"idx"/"list"/"origin"/"match", value), ...]
        :param match_func: 可选，处理 match 类型的自定义函数，参数(data, val)
        :param nuxt_json: 原始根节点，处理 origin 时需要
        :return: 解析结果或 None
        """
        try:
            for typ, val in chain:
                if typ == "list":
                    if not isinstance(data, list):
                        return None
                    data = data[val]
                elif typ == "key":
                    if not isinstance(data, dict):
                        return None
                    data = data[val]
                elif typ == "idx":
                    if isinstance(data, list) and data:
                        data = data[val]
                    else:
                        return None
                elif typ == "origin":
                    # 严格按原实现：data = nuxt_json[data]
                    if nuxt_json is None:
                        return None
                    try:
                        data = nuxt_json[data]
                    except Exception:
                        return None
                elif typ == "match":
                    if match_func:
                        data = match_func(data, val)
                    else:
                        return None
                else:
                    return None
            return data
        except Exception as e:
            print(f"resolve_json_chain 解析失败: {str(e)}")
            return None
