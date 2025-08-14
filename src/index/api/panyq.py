from ..base import BaseSearch
import requests
import re
import json
import os
import time
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional
from threading import Lock, RLock
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter

class PanyqSearch(BaseSearch):
    """盘友圈搜索实现"""
    
    # 常量定义
    DEFAULT_TIMEOUT = 15
    MAX_CONCURRENCY = 100
    MAX_RETRIES = 0
    DEBUG_LOG = False
    CONFIG_FILE_NAME = "panyq_config.json"
    BASE_URL = "https://panyq.com"
    ENABLE_REFERER_CHECK = True
    
    ACTION_ID_KEYS = [
        "credential_action_id",     # 获取凭证用的ID
        "intermediate_action_id",   # 中间步骤用的ID
        "final_link_action_id",     # 获取最终链接用的ID
    ]
    
    ALLOWED_REFERERS = [
        "https://dm.xueximeng.com",
        "http://localhost",
    ]
    
    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self.client = self._create_http_client()
        self.action_id_cache = {}
        self.final_link_cache = {}
        self.search_result_cache = {}
        self.action_id_lock = RLock()
        self.final_link_lock = RLock()
        self.search_result_lock = RLock()
        
        # 启动缓存清理
        self._start_cache_cleaner()
    
    def _create_http_client(self):
        """创建HTTP客户端"""
        
        session = requests.Session()
        
        # 配置适配器，增加连接池大小
        adapter = HTTPAdapter(
            pool_connections=20,  # 连接池中的连接数
            pool_maxsize=50,      # 连接池最大连接数
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # session.verify = False  # 忽略HTTPS证书验证
        session.timeout = self.DEFAULT_TIMEOUT
        return session
    
    def search(self, keyword: str, ext: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """搜索盘友圈资源并返回结构化结果
        
        Args:
            keyword: 搜索关键词
            ext: 扩展参数
            
        Returns:
            标准化的结果字典，格式与yunso.py一致
        """
        if ext is None:
            ext = {}
            
        if self.DEBUG_LOG:
            print(f"panyq: ext 参数内容: {ext}")
            
        # 检查搜索结果缓存
        cache_key = f"search:{keyword}"
        with self.search_result_lock:
            if cache_key in self.search_result_cache:
                if self.DEBUG_LOG:
                    print(f"panyq: 缓存命中搜索结果: {keyword}")
                return self._format_results(self.search_result_cache[cache_key])
        
        # 请求来源检查
        if self.ENABLE_REFERER_CHECK and ext:
            referer = ext.get("referer", "")
            allowed = any(referer.startswith(r) for r in self.ALLOWED_REFERERS)
            
            if not allowed:
                if self.DEBUG_LOG:
                    print(f"panyq: 拒绝来自 {referer} 的请求")
                return {"list": [], "channelInfo": self._get_channel_info()}
        
        try:
            results = self._do_search(keyword, ext)
            
            # 缓存结果
            with self.search_result_lock:
                self.search_result_cache[cache_key] = results
                
            return self._format_results(results)
            
        except Exception as e:
            print(f"panyq: 搜索失败: {str(e)}")
            return {"list": [], "channelInfo": self._get_channel_info()}
    
    def _format_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """将结果格式化为yunso.py的格式"""
        return {
            "list": [{
                "messageId": item.get("unique_id", ""),
                "title": item.get("title", ""),
                "pubDate": item.get("datetime", ""),
                "content": item.get("content", ""),
                "image": "",
                "cloudLinks": [{
                    "link": link["url"],
                    "cloudType": link["type"]
                } for link in item.get("links", [])],
                "tags": [],
                "magnetLink": "",
                "channel": "盘友圈",
                "channelId": "panyq"
            } for item in results],
            "channelInfo": self._get_channel_info(),
            "id": "panyq",
            "index": 1001
        }
    
    def _get_channel_info(self) -> Dict[str, Any]:
        """获取频道信息"""
        return {
            "id": "panyq",
            "name": "盘友圈",
            "index": 1001,
            "channelLogo": ""
        }
    
    def _do_search(self, keyword: str, ext: Dict[str, Any]) -> List[Dict[str, Any]]:
        """实际的搜索实现"""
        if self.DEBUG_LOG:
            print(f"panyq: searching for {keyword}")
            
        # 获取Action IDs
        action_ids = self._get_or_discover_action_ids()
        if not action_ids:
            raise Exception("获取Action ID失败")
            
        # 获取凭证
        credentials = self._get_credentials(keyword, action_ids[self.ACTION_ID_KEYS[0]])
        if not credentials:
            # 尝试刷新Action ID并重试
            action_ids = self._discover_action_ids()
            credentials = self._get_credentials(keyword, action_ids[self.ACTION_ID_KEYS[0]])
            if not credentials:
                raise Exception("获取搜索凭证失败")
                
        # 获取搜索结果
        hits, max_page_num = self._get_search_results(credentials["sign"], 1)
        if not hits:
            if self.DEBUG_LOG:
                print(f"panyq: no results found for {keyword}")
            return []
            
        # 如果有多页结果，并发获取其他页的数据
        if max_page_num > 1:
            if self.DEBUG_LOG:
                print(f"panyq: found {max_page_num} pages, fetching additional pages...")
                
            if max_page_num >= 3:
                max_page_num = 3
                
            with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENCY) as executor:
                futures = []
                for page in range(2, max_page_num + 1):
                    futures.append(executor.submit(self._get_search_results, credentials["sign"], page))
                    
                for future in as_completed(futures):
                    try:
                        page_hits, _ = future.result()
                        hits.extend(page_hits)
                    except Exception as e:
                        print(f"panyq: 获取页面失败: {str(e)}")
                        
            if self.DEBUG_LOG:
                print(f"panyq: total {len(hits)} results from all pages")
                
        # 并发处理每个搜索结果
        results = []
        with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENCY) as executor:
            futures = []
            for i, hit in enumerate(hits):
                futures.append(executor.submit(self._process_hit, hit, i, action_ids, credentials))
                
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    print(f"panyq: 处理结果失败: {str(e)}")
                    
        # 使用关键词过滤结果
        filtered_results = self._filter_results_by_keyword(results, keyword)
        
        if self.DEBUG_LOG:
            print(f"panyq: returning {len(filtered_results)} filtered results")
            
        return filtered_results
    
    def _process_hit(self, hit: Dict[str, Any], index: int, action_ids: Dict[str, str], credentials: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """处理单个搜索结果"""
        # 执行中间状态确认
        if not self._perform_intermediate_step(
            action_ids[self.ACTION_ID_KEYS[1]],
            credentials["hash"],
            credentials["sha"],
            hit["eid"]
        ):
            print(f"panyq: intermediate step failed for {hit['eid']}")
            return None
            
        # 获取最终链接
        final_link = self._get_final_link(
            action_ids[self.ACTION_ID_KEYS[2]],
            hit["eid"]
        )
        
        if not final_link:
            return None
            
        # 确定链接类型
        link_type = self._determine_link_type(final_link)
        
        # 创建结果
        return {
            "unique_id": f"panyq-{index}",
            "title": self._extract_title(hit["desc"]),
            "content": self._clean_escaped_html(hit["desc"]),
            "links": [{
                "url": final_link,
                "type": link_type,
                "password": self._extract_password(final_link, link_type)
            }],
            "datetime": ""
        }
    
    def _get_or_discover_action_ids(self) -> Dict[str, str]:
        """获取或发现Action ID"""
        with self.action_id_lock:
            if len(self.action_id_cache) >= len(self.ACTION_ID_KEYS):
                return self.action_id_cache.copy()
                
        return self._discover_action_ids()
    
    def _discover_action_ids(self) -> Dict[str, str]:
        """发现Action ID"""
        # 尝试从缓存文件加载
        final_ids = self._load_action_ids_from_file()
        if final_ids and len(final_ids) == len(self.ACTION_ID_KEYS):
            if self.DEBUG_LOG:
                print("panyq: loaded Action IDs from file cache")
            with self.action_id_lock:
                self.action_id_cache.update(final_ids)
            return final_ids
            
        # 从网站获取潜在的Action ID
        potential_ids = self._find_potential_action_ids()
        if not potential_ids:
            raise Exception("未找到潜在的Action ID")
            
        if self.DEBUG_LOG:
            print(f"panyq: 找到 {len(potential_ids)} 个潜在的 Action ID")
            if potential_ids:
                print(f"panyq: 样例ID: {potential_ids[0]}")
                
        final_ids = {}
        
        # 1. 验证credential_action_id
        if self.DEBUG_LOG:
            print("panyq: validating credential_action_id...")
            
        credential_id = None
        for id in potential_ids:
            if self._validate_credential_id(id):
                credential_id = id
                break
                
        if not credential_id:
            raise Exception("未能验证credential_action_id")
            
        final_ids[self.ACTION_ID_KEYS[0]] = credential_id
        
        # 获取测试凭证用于后续验证
        test_creds = self._get_credentials("test", credential_id)
        if not test_creds:
            raise Exception("获取测试凭证失败")
            
        if self.DEBUG_LOG:
            print(f"panyq: 获取到测试凭证: sign={test_creds['sign'][:10]}..., hash={test_creds['hash'][:10]}..., sha={test_creds['sha'][:10]}...")
            
        # 从剩余ID中排除已使用的ID
        remaining_ids = [id for id in potential_ids if id != credential_id]
        
        # 2. 验证intermediate_action_id
        if self.DEBUG_LOG:
            print(f"panyq: validating intermediate_action_id ({len(remaining_ids)} candidates)...")
            
        intermediate_id = None
        for id in reversed(remaining_ids):
            if self._validate_intermediate_id(id, test_creds["hash"], test_creds["sha"]):
                intermediate_id = id
                break
                
        if not intermediate_id:
            raise Exception("未能验证intermediate_action_id")
            
        final_ids[self.ACTION_ID_KEYS[1]] = intermediate_id
        
        # 获取测试EID
        test_hits, _ = self._get_search_results(test_creds["sign"], 1)
        if not test_hits:
            raise Exception("获取测试EID失败: 无搜索结果")
            
        test_eid = test_hits[0]["eid"]
        
        if self.DEBUG_LOG:
            print(f"panyq: 获取到测试EID: {test_eid}")
            
        # 从剩余ID中排除已使用的ID
        remaining_ids = [id for id in remaining_ids if id != intermediate_id]
        
        # 3. 验证final_link_action_id
        if self.DEBUG_LOG:
            print(f"panyq: validating final_link_action_id ({len(remaining_ids)} candidates)...")
            
        final_link_id = None
        for id in remaining_ids:
            # 执行中间步骤
            try:
                self._perform_intermediate_step(intermediate_id, test_creds["hash"], test_creds["sha"], test_eid)
            except Exception as e:
                print(f"panyq: 中间步骤执行失败, 继续尝试下一个ID: {str(e)}")
                continue
                
            if self._validate_final_link_id(id, test_eid):
                final_link_id = id
                break
                
        if not final_link_id and len(remaining_ids) == 1 and len(potential_ids) == 3:
            # 尝试交换intermediate_action_id和final_link_action_id
            if self.DEBUG_LOG:
                print("panyq: final_link_action_id验证失败，尝试交换intermediate_action_id和final_link_action_id...")
                
            old_inter_id = final_ids[self.ACTION_ID_KEYS[1]]
            final_ids[self.ACTION_ID_KEYS[1]] = remaining_ids[0]
            final_ids[self.ACTION_ID_KEYS[2]] = old_inter_id
            
            try:
                self._perform_intermediate_step(final_ids[self.ACTION_ID_KEYS[1]], test_creds["hash"], test_creds["sha"], test_eid)
                if self._validate_final_link_id(final_ids[self.ACTION_ID_KEYS[2]], test_eid):
                    final_link_id = final_ids[self.ACTION_ID_KEYS[2]]
                    if self.DEBUG_LOG:
                        print("panyq: 交换ID后验证成功!")
            except Exception as e:
                if self.DEBUG_LOG:
                    print(f"panyq: 交换后中间步骤执行失败: {str(e)}")
                    
        if not final_link_id:
            raise Exception("未能验证final_link_action_id")
            
        final_ids[self.ACTION_ID_KEYS[2]] = final_link_id
        
        # 保存到内存缓存
        with self.action_id_lock:
            self.action_id_cache.update(final_ids)
            
        # 保存到文件缓存
        try:
            self._save_action_ids_to_file(final_ids)
        except Exception as e:
            print(f"panyq: 保存Action IDs到文件失败: {str(e)}")
            
        if self.DEBUG_LOG:
            print("panyq: all Action IDs validated successfully:")
            for key in self.ACTION_ID_KEYS:
                print(f"panyq:   {key} = {final_ids[key]}")
                
        return final_ids
    
    def _find_potential_action_ids(self) -> List[str]:
        """从网站获取潜在的Action ID"""
        # 请求网站首页
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            }
            resp = self.client.get(self.BASE_URL, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            raise Exception(f"请求网站首页失败: {str(e)}")
        # 提取JS文件路径
        js_regex = re.compile(r'<script src="(/_next/static/[^"]+\.js)"')
        matches = js_regex.findall(resp.text)
        if not matches:
            raise Exception("未找到JS文件")
        # 收集所有潜在的Action ID
        id_set = set()
        id_regex = re.compile(r'["\']([a-f0-9]{40})["\']{1}')
        
        for js_path in matches:
            js_url = self.BASE_URL + js_path
            try:
                js_headers = {
                    "Referer": self.BASE_URL,
                    "Origin": self.BASE_URL,
                    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
                }
                js_resp = self.client.get(js_url, headers=js_headers)
                js_resp.raise_for_status()
                id_matches = id_regex.findall(js_resp.text)
                id_set.update(id_matches)
            except Exception as e:
                print(str(e))
                continue
                
        if self.DEBUG_LOG:
            print(f"panyq: found {len(id_set)} potential Action IDs")
        return list(id_set)
    
    def _validate_credential_id(self, action_id: str) -> bool:
        """验证credential_action_id"""
        try:
            creds = self._get_credentials("test", action_id)
            return creds is not None
        except Exception:
            return False
    
    def _validate_intermediate_id(self, action_id: str, hash_val: str, sha_val: str) -> bool:
        """验证intermediate_action_id"""
        try:
            self._perform_intermediate_step(action_id, hash_val, sha_val, "fake_eid_for_validation")
            return True
        except Exception:
            return False
    
    def _validate_final_link_id(self, action_id: str, eid: str) -> bool:
        """验证final_link_action_id"""
        try:
            response_text = self._get_raw_final_link_response(action_id, eid)
            if not response_text:
                return False
                
            # 检查原始响应中是否包含链接相关的关键词
            keywords = ["http", "magnet", "aliyundrive", '"url"']
            return any(kw in response_text for kw in keywords)
        except Exception:
            return False
    
    def _do_request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """发送HTTP请求并支持重试"""
        max_retries = kwargs.pop('max_retries', self.MAX_RETRIES)
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                backoff = min(2 ** (attempt - 1) * 0.5, 5)  # 指数退避，最大5秒
                time.sleep(backoff)
                if self.DEBUG_LOG:
                    print(f"panyq: 重试请求 #{attempt}，等待 {backoff}秒")
                    
            try:
                resp = self.client.request(method, url, **kwargs)
                return resp
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                if attempt == max_retries:
                    raise
                continue
                
        raise Exception(f"请求失败，重试{max_retries}次后仍然失败")
    
    def _get_raw_final_link_response(self, action_id: str, eid: str) -> str:
        """获取最终链接的原始响应文本"""
        cache_key = f"{action_id}:{eid}"
        with self.final_link_lock:
            if cache_key in self.final_link_cache:
                if self.DEBUG_LOG:
                    print(f"panyq: 缓存命中 raw final link: {eid}")
                return self.final_link_cache[cache_key]
                
        # 构建URL
        final_url = f"{self.BASE_URL}/go/{eid}"
        
        # 构建请求体
        payload = f'[{{"eid":"{eid}"}}]'
        
        # 创建请求
        headers = {
            "Content-Type": "text/plain;charset=UTF-8",
            "next-action": action_id,
            "Referer": final_url,
            "Origin": self.BASE_URL,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        
        try:
            resp = self._do_request_with_retry("POST", final_url, data=payload, headers=headers)
            response_text = resp.text
            
            # 保存到缓存
            with self.final_link_lock:
                self.final_link_cache[cache_key] = response_text
                
            return response_text
        except Exception as e:
            if self.DEBUG_LOG:
                print(f"panyq: network error: {str(e)}")
            raise
    
    def _get_credentials(self, query: str, action_id: str) -> Optional[Dict[str, str]]:
        """获取搜索凭证"""
        payload = f'[{{"cat":"all","query":"{query}","pageNum":1}}]'
        
        headers = {
            "Content-Type": "text/plain;charset=UTF-8",
            "next-action": action_id,
            "Referer": self.BASE_URL,
            "Origin": self.BASE_URL,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        
        try:
            resp = self._do_request_with_retry("POST", self.BASE_URL, data=payload, headers=headers)
            
            # 使用正则表达式提取凭证
            sign_match = re.search(r'"sign":"([^"]+)"', resp.text)
            sha_match = re.search(r'"sha":"([a-f0-9]{64})"', resp.text)
            hash_match = re.search(r'"hash","([^"]+)"', resp.text)
            
            if not sign_match or not sha_match or not hash_match:
                raise Exception("提取凭证失败")
                
            return {
                "sign": sign_match.group(1),
                "sha": sha_match.group(1),
                "hash": hash_match.group(1)
            }
        except Exception as e:
            if self.DEBUG_LOG:
                print(f"panyq: 获取凭证失败: {str(e)}")
            raise
    
    def _get_search_results(self, sign: str, page_num: int) -> tuple[List[Dict[str, Any]], int]:
        """获取搜索结果列表"""
        search_url = f"{self.BASE_URL}/api/search?sign={sign}&page={page_num}"
        
        headers = {
            "Referer": self.BASE_URL,
            "Origin": self.BASE_URL,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        
        # 从缓存中获取credential_action_id并添加到请求头
        with self.action_id_lock:
            if self.ACTION_ID_KEYS[0] in self.action_id_cache:
                headers["next-action"] = self.action_id_cache[self.ACTION_ID_KEYS[0]]
        
        try:
            resp = self._do_request_with_retry("GET", search_url, headers=headers)
            data = resp.json()
            
            hits = data.get("data", {}).get("hits", [])
            max_page_num = data.get("data", {}).get("maxPageNum", 1)
            
            return hits, max_page_num
        except Exception as e:
            if self.DEBUG_LOG:
                print(f"panyq: 获取搜索结果失败: {str(e)}")
            raise
    
    def _perform_intermediate_step(self, action_id: str, hash_val: str, sha_val: str, eid: str) -> bool:
        """执行中间状态确认"""
        intermediate_url = f"{self.BASE_URL}/search/{hash_val}"
        
        # 构建请求体
        payload = f'[{{"eid":"{eid}","sha":"{sha_val}","page_num":"1"}}]'
        
        headers = {
            "Content-Type": "text/plain;charset=UTF-8",
            "next-action": action_id,
            "Referer": intermediate_url,
            "Origin": self.BASE_URL,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        
        try:
            resp = self._do_request_with_retry("POST", intermediate_url, data=payload, headers=headers)
            return resp.status_code == 200
        except Exception as e:
            if self.DEBUG_LOG:
                print(f"panyq: 中间步骤执行失败: {str(e)}")
            return False
    
    def _get_final_link(self, action_id: str, eid: str) -> Optional[str]:
        """获取最终链接"""
        cache_key = f"link:{action_id}:{eid}"
        with self.final_link_lock:
            if cache_key in self.final_link_cache:
                if self.DEBUG_LOG:
                    print(f"panyq: 缓存命中最终链接: {eid}")
                return self.final_link_cache[cache_key]
                
        # 获取原始响应
        try:
            response_text = self._get_raw_final_link_response(action_id, eid)
        except Exception:
            return None
            
        # 尝试从JSON中提取URL
        lines = response_text.split("\n")
        final_link = None
        
        if lines:
            last_line = lines[-1]
            try:
                link_data = json.loads(last_line)
                if isinstance(link_data, list) and len(link_data) > 1:
                    if isinstance(link_data[1], dict):
                        final_link = link_data[1].get("url")
            except json.JSONDecodeError:
                pass
                
        # 如果JSON解析失败，尝试使用正则表达式
        if not final_link:
            url_match = re.search(r'(https?://[^\s"\']+|magnet:\?[^\s"\']+)', response_text)
            if url_match:
                final_link = url_match.group(0)
                
        if not final_link:
            if self.DEBUG_LOG:
                print("panyq: 提取链接失败")
            return None
            
        # 保存链接到缓存
        with self.final_link_lock:
            self.final_link_cache[cache_key] = final_link
            
        return final_link
    
    def _determine_link_type(self, url: str) -> str:
        """根据URL确定链接类型"""
        lower_url = url.lower()
        
        if "pan.baidu.com" in lower_url:
            return "baidu"
        elif "alipan.com" in lower_url or "aliyundrive.com" in lower_url:
            return "aliyun"
        elif "pan.xunlei.com" in lower_url:
            return "xunlei"
        elif "cloud.189.cn" in lower_url:
            return "tianyi"
        elif "caiyun.139.com" in lower_url or "yun.139.com" in lower_url:
            return "mobile"
        elif "pan.quark.cn" in lower_url:
            return "quark"
        elif "115.com" in lower_url:
            return "115"
        elif "weiyun.com" in lower_url:
            return "weiyun"
        elif "lanzou" in lower_url:
            return "lanzou"
        elif "jianguoyun.com" in lower_url:
            return "jianguoyun"
        elif "123pan.com" in lower_url:
            return "123"
        elif "drive.uc.cn" in lower_url:
            return "uc"
        elif "mypikpak.com" in lower_url:
            return "pikpak"
        elif lower_url.startswith("magnet:"):
            return "magnet"
        elif lower_url.startswith("ed2k:"):
            return "ed2k"
        else:
            return "others"
    
    def _extract_password(self, url: str, link_type: str) -> str:
        """从URL或内容中提取密码"""
        if link_type == "baidu":
            if "?pwd=" in url:
                pwd = url.split("?pwd=")[1]
                return pwd[:4] if len(pwd) >= 4 else pwd
        elif link_type == "aliyun":
            if "password=" in url:
                pwd = url.split("password=")[1]
                return pwd.split("&")[0] if "&" in pwd else pwd
        return ""
    
    def _clean_escaped_html(self, text: str) -> str:
        """清理HTML转义字符"""
        replacers = {
            r'\u003Cmark\u003E': '',
            r'\u003C/mark\u003E': '',
            r'\u003Cb\u003E': '',
            r'\u003C/b\u003E': '',
            r'\u003Cem\u003E': '',
            r'\u003C/em\u003E': '',
            r'\u003Cstrong\u003E': '',
            r'\u003C/strong\u003E': '',
            r'\u003Ci\u003E': '',
            r'\u003C/i\u003E': '',
            r'\u003Cu\u003E': '',
            r'\u003C/u\u003E': '',
            r'\u003Cbr\u003E': ' ',
            r'\u003Cbr/\u003E': ' ',
            r'\u003Cbr /\u003E': ' ',
            '<mark>': '',
            '</mark>': '',
            '<b>': '',
            '</b>': '',
            '<em>': '',
            '</em>': '',
            '<strong>': '',
            '</strong>': '',
            '<i>': '',
            '</i>': '',
            '<u>': '',
            '</u>': '',
            '<br>': ' ',
            '<br/>': ' ',
            '<br />': ' '
        }
        
        result = text
        for old, new in replacers.items():
            result = result.replace(old, new)
            
        return result
    
    def _extract_title(self, desc: str) -> str:
        """从描述中提取标题"""
        clean_desc = self._clean_escaped_html(desc)
        
        # 尝试匹配《》内的内容
        title_match = re.search(r'《([^》]+)》', clean_desc)
        if title_match:
            return title_match.group(1)
            
        # 尝试匹配【】内的内容
        title_match = re.search(r'【([^】]+)】', clean_desc)
        if title_match:
            return title_match.group(1)
            
        # 尝试提取开头的一段（到第一个分隔符为止）
        parts = clean_desc.split("✔")
        if parts and parts[0]:
            return parts[0].strip()
            
        # 如果以上方法都无法提取标题，则取前30个字符作为标题
        if len(clean_desc) > 30:
            return clean_desc[:30].strip() + "..."
            
        return clean_desc.strip()
    
    def _filter_results_by_keyword(self, results: List[Dict[str, Any]], keyword: str) -> List[Dict[str, Any]]:
        """使用关键词过滤结果"""
        # 这里实现与Go代码相同的过滤逻辑
        return results
    
    def _start_cache_cleaner(self):
        """启动缓存清理器"""
        import threading
        
        def cleaner():
            while True:
                time.sleep(1800)  # 30分钟
                if self.DEBUG_LOG:
                    print("panyq: 开始清理缓存")
                    
                with self.final_link_lock:
                    self.final_link_cache = {}
                    
                with self.search_result_lock:
                    self.search_result_cache = {}
                    
                if self.DEBUG_LOG:
                    print("panyq: 缓存清理完成")
                    
        thread = threading.Thread(target=cleaner, daemon=True)
        thread.start()
    
    def _load_action_ids_from_file(self) -> Dict[str, str]:
        """从文件加载Action IDs"""
        config_path = Path(self.CONFIG_FILE_NAME)
        if not config_path.exists():
            return {}
            
        try:
            with open(config_path, 'r') as f:
                ids = json.load(f)
                
            # 验证所有必需的键是否存在
            for key in self.ACTION_ID_KEYS:
                if key not in ids:
                    raise Exception(f"缓存文件中缺少键: {key}")
                    
            return ids
        except Exception as e:
            if self.DEBUG_LOG:
                print(f"panyq: 加载Action IDs失败: {str(e)}")
            return {}
    
    def _save_action_ids_to_file(self, ids: Dict[str, str]):
        """保存Action IDs到文件"""
        config_path = Path(self.CONFIG_FILE_NAME)
        try:
            with open(config_path, 'w') as f:
                json.dump(ids, f)
        except Exception as e:
            raise Exception(f"保存Action IDs失败: {str(e)}")