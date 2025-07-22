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
