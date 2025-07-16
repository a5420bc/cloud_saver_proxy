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