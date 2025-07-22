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

"""
    baiduPan: /https?:\/\/(?:pan|yun)\.baidu\.com\/[^\s<>"]+/g,
    tianyi: /https?:\/\/cloud\.189\.cn\/[^\s<>"]+/g,
    aliyun: /https?:\/\/\w+\.(?:alipan|aliyundrive)\.com\/[^\s<>"]+/g,
    // pan115有两个域名 115.com 和 anxia.com 和 115cdn.com
    pan115: /https?:\/\/(?:115|anxia|115cdn)\.com\/s\/[^\s<>"]+/g,
    // 修改为匹配所有以123开头的域名
    // eslint-disable-next-line no-useless-escape
    pan123: /https?:\/\/(?:www\.)?123[^\/\s<>"]+\.com\/s\/[^\s<>"]+/g,
    quark: /https?:\/\/pan\.quark\.cn\/[^\s<>"]+/g,
    yidong: /https?:\/\/caiyun\.139\.com\/[^\s<>"]+/g,
"""