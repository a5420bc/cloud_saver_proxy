from datetime import datetime
from functools import lru_cache
import json
import time
import logging

import requests

logger = logging.getLogger(__name__)

class Bangumi(object):
    """
    https://bangumi.github.io/api/
    """

    _urls = {
        "calendar": "calendar",
        "detail": "v0/subjects/%s",
    }
    _base_url = "https://api.bgm.tv/"
    _page_num = 50

    def __init__(self):
        pass

    @classmethod
    @lru_cache(maxsize=128)
    def __invoke(cls, url, **kwargs):
        req_url = cls._base_url + url
        params = {}
        if kwargs:
            params.update(kwargs)
        try:
            resp = requests.get(req_url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Bangumi API请求失败: {e}")
            return None

    def calendar(self):
        """
        获取每日放送
        """
        return self.__invoke(self._urls["calendar"], _ts=datetime.strftime(datetime.now(), '%Y%m%d'))

    def detail(self, bid):
        """
        获取番剧详情
        """
        return self.__invoke(self._urls["detail"] % bid, _ts=datetime.strftime(datetime.now(), '%Y%m%d'))

    @staticmethod
    def _to_douban_card(item):
        """
        转换为豆瓣风格卡片结构
        """
        # rating
        rating = item.get("rating") or {}
        rating_count = rating.get("total") or rating.get("count") or 0
        rating_value = rating.get("score") or rating.get("value") or 0
        # 豆瓣 star_count 约等于 value/2，四舍五入到0.5
        try:
            star_count = round(float(rating_value) / 2 * 2) / 2 if rating_value else 0
        except Exception:
            star_count = 0
        # title
        title = item.get("name_cn") or item.get("name") or ""
        # pic
        images = item.get("images") or {}
        pic_large = images.get("large") or images.get("common") or ""
        pic_normal = images.get("large") or images.get("normal") or images.get("medium") or images.get("common") or ""
        # is_new
        air_date = item.get("air_date") or ""
        is_new = False
        if air_date:
            try:
                # 近30天内首播算新
                from datetime import datetime, timedelta
                dt = datetime.strptime(air_date, "%Y-%m-%d")
                is_new = (datetime.now() - dt).days <= 30
            except Exception:
                is_new = False
        # uri
        uri = item.get("url")
        # episodes_info
        eps = item.get("eps") or []
        eps_count = item.get("eps_count") or len(eps)
        episodes_info = f"{eps_count}集全" if eps_count else ""
        # card_subtitle
        year = air_date[:4] if air_date else ""
        weekday = item.get("weekday") or ""
        
        card_subtitle = f"{year} /{weekday}" 
        # type
        type_ = "tv"
        # id
        id_ = str(item.get("id") or "")
        return {
            "rating": {
                "count": rating_count,
                "max": 10,
                "star_count": star_count,
                "value": rating_value
            },
            "title": title,
            "pic": {
                "large": pic_large,
                "normal": pic_normal
            },
            "is_new": is_new,
            "uri": uri,
            "episodes_info": episodes_info,
            "card_subtitle": card_subtitle,
            "type": type_,
            "id": id_
        }

    def get_bangumi_calendar(self, page=1, week=None):
        """
        获取每日放送
        """
        start_time = time.time()
        
        # API请求阶段
        api_start = time.time()
        infos = self.calendar()
        api_time = time.time() - api_start
        logger.debug(f"Bangumi API请求耗时: {api_time:.3f}s")
        
        if not infos:
            return []
            
        # 数据处理阶段
        process_start = time.time()
        ret_list = []
        
        # 记录原始数据量
        total_items = sum(len(info.get("items", [])) for info in infos)
        logger.debug(f"开始处理数据，总条目数: {total_items}")
        
        for info in infos:
            weeknum = info.get("weekday", {}).get("id")
            if week and int(weeknum) != int(week):
                continue
            weekday = info.get("weekday").get("cn")
            items = info.get("items")
            for item in items:
                item["weekday"] = weekday
                ret_list.append(self._to_douban_card(item))
        
        process_time = time.time() - process_start
        total_time = time.time() - start_time
        logger.debug(f"数据处理耗时: {process_time:.3f}s")
        logger.debug(f"总耗时: {total_time:.3f}s, 返回结果数: {len(ret_list)}")
        
        return {
            "success": True,
            "code": 0,
            "data": ret_list,
            "message": "操作成功"
        }
