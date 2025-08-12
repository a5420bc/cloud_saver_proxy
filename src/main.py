from contextlib import asynccontextmanager
import asyncio
import json
import importlib
import pkgutil
import yaml
from pathlib import Path
from typing import Dict, Type
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from resource.bangumi import Bangumi
import httpx
from httpx import Timeout
from index.base import BaseSearch
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# 限制第三方库的日志级别
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
# 加载配置文件
with open(Path(__file__).parent.parent / "config.yaml") as f:
    config = yaml.safe_load(f)

# 服务配置
TARGET_SERVICE = config["target_service"]
INTERCEPT_PATHS = config["intercept_paths"]

# 更长的全局超时设置(300秒=5分钟)
HTTPX_TIMEOUT = 60


class PluginManager:
    def __init__(self):
        # {name: {'cls': cls, 'enabled': bool}}
        self.search_plugins: Dict[str, Dict] = {}

    def discover_plugins(self, disabled_plugins: list = None):
        """自动发现api目录下的搜索插件，支持vde51/taiqiongle双实例"""
        disabled_plugins = disabled_plugins or []
        api_path = Path(__file__).parent / "index" / "api"
        print(f"搜索插件目录: {api_path}")

        if not api_path.exists():
            print(f"错误: 插件目录不存在 {api_path}")
            return

        for finder, name, _ in pkgutil.iter_modules([str(api_path)]):
            print(f"发现模块: {name}")
            try:
                module = importlib.import_module(f"index.api.{name}")
                print(f"尝试加载模块: {name}")
                for attr in dir(module):
                    try:
                        cls = getattr(module, attr)
                        if (isinstance(cls, type) and
                            issubclass(cls, BaseSearch) and
                                cls != BaseSearch):
                            print(f"找到搜索插件类: {cls.__name__}")
                            if name == "vde51":
                                # 注册vde51和taiqiongle两个实例
                                for site_key in ["vde51", "taiqiongle"]:
                                    if site_key in disabled_plugins:
                                        print(f"插件 {site_key} 被禁用")
                                        continue
                                    self.search_plugins[site_key] = {
                                        'cls': cls,
                                        'enabled': site_key not in disabled_plugins,
                                        'site': "51vde" if site_key == "vde51" else "taiqiongle"
                                    }
                                    print(f"成功注册插件: {site_key}")
                            else:
                                if name in disabled_plugins:
                                    print(f"插件 {name} 被禁用")
                                    continue
                                self.search_plugins[name] = {
                                    'cls': cls,
                                    'enabled': name not in disabled_plugins
                                }
                                print(f"成功注册插件: {name}")
                    except Exception as e:
                        print(f"检查类 {attr} 时出错: {str(e)}")
                        continue
            except Exception as e:
                print(f"加载插件 {name} 失败: {str(e)}")
                continue

    async def init_plugins(self, app: FastAPI):
        """初始化所有启用的插件"""
        self.plugin_instances = {}  # 存储插件实例

        for name, plugin in self.search_plugins.items():
            if not plugin['enabled']:
                continue
            cls = plugin['cls']
            # 特殊处理aipan需要多个实例
            if name == 'aipan':
                self.plugin_instances[name] = [
                    cls(source_id=i) for i in range(1, 9)]
                # 仅aipan需要挂载到app.state
                app.state.aipan_searches = self.plugin_instances[name]
            elif name in ['vde51', 'taiqiongle']:
                # 分别初始化site参数
                self.plugin_instances[name] = cls(
                    site=plugin.get('site', '51vde'))
            else:
                self.plugin_instances[name] = cls()


plugin_manager = PluginManager()


# 在模块加载时初始化插件
disabled_plugins = config.get("disabled_plugins", [])
plugin_manager.discover_plugins(disabled_plugins)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 只在应用启动和关闭时触发一次"""
    # 初始化插件实例
    await plugin_manager.init_plugins(app)
    print(
        f"已初始化插件: {[name for name, p in plugin_manager.search_plugins.items() if p['enabled']]}")
    yield
    # 应用关闭时的清理逻辑可以放在这里

app = FastAPI(lifespan=lifespan)


# 加载配置文件
with open(Path(__file__).parent.parent / "config.yaml") as f:
    config = yaml.safe_load(f)

# 服务配置
TARGET_SERVICE = config["target_service"]
INTERCEPT_PATHS = config["intercept_paths"]


async def fetch_external_data(keyword: str, use_all_plugins: bool = False):
    """从多个数据源并发获取外部数据
    :param keyword: 搜索关键词
    :param use_all_plugins: 是否使用所有插件，False时只使用指定插件
    """
    # 准备搜索任务
    search_tasks = []

    # 指定插件列表
    SPECIFIC_PLUGINS = [
        'vde51', 'panws', 'pansearch',
        'alipanx', 'rrdynb', 'xzys', 'hunhepan',
        'qupansou', 'libvio', 'fox4k', 'yunso', 'vcsoso'
    ]

    # 通过plugin_manager获取所有启用的搜索插件实例
    for name, plugin in plugin_manager.search_plugins.items():
        if not plugin['enabled']:
            continue
        # 如果不使用所有插件且当前插件不在指定列表中，则跳过
        if not use_all_plugins and name not in SPECIFIC_PLUGINS:
            print(f"{name}不在指定列表中")
            continue
        if name == 'aipan':
            # 特殊处理aipan的多个实例
            search_tasks.extend(
                asyncio.to_thread(
                    lambda s=search, n=name: (
                        f"{n}_{s.source_id}", time.time(), s.search(keyword))
                )
                for search in plugin_manager.plugin_instances[name]
            )
            pass
        else:
            search_inst = plugin_manager.plugin_instances.get(name)
            if search_inst:
                search_tasks.append(
                    asyncio.to_thread(
                        lambda s=search_inst, n=name: (
                            n, time.time(), s.search(keyword))
                    )
                )

    # 执行并发搜索
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # 过滤有效结果并记录耗时
    valid_results = []
    time_records = []

    for result in search_results:
        if isinstance(result, Exception):
            logger.error(f"搜索任务失败: {str(result)}")
            continue
        if not result or not isinstance(result, tuple) or len(result) != 3:
            continue
        name, start_time, data = result
        if not data or not data.get("list"):
            continue
        valid_results.append(data)
        elapsed = time.time() - start_time
        time_records.append((name, elapsed))
        logger.debug(f"接口[{name}] 耗时: {elapsed:.3f}秒")

    # 输出统计信息
    if time_records:
        names, times = zip(*time_records)
        total_time = sum(times)
        avg_time = total_time / len(time_records)
        min_time = min(time_records, key=lambda x: x[1])
        max_time = max(time_records, key=lambda x: x[1])
        logger.debug(f"接口调用统计:")
        logger.debug(f"总调用次数: {len(time_records)}")
        logger.debug(f"总耗时: {total_time:.3f}秒")
        logger.debug(f"平均耗时: {avg_time:.3f}秒")
        logger.debug(f"最快接口: [{min_time[0]}] {min_time[1]:.3f}秒")
        logger.debug(f"最慢接口: [{max_time[0]}] {max_time[1]:.3f}秒")

    return valid_results


@app.middleware("http")
async def proxy_middleware(request: Request, call_next):
    path = request.url.path
    query = str(request.url.query)

    # 新增：拦截 /api/douban/hot 且 category=bangumi，直接返回指定结果
    if path == "/api/douban/hot":
        import urllib.parse
        query_params = dict(request.query_params)
        if query_params.get("category") == "bangumi":
            ret = Bangumi().get_bangumi_calendar()
            return JSONResponse(
                ret,
                status_code=200
            )

    # 新增：拦截 /assets/douban-xxxx.js，转发并在数组末尾插入 Bangumi 分类
    import re
    if re.fullmatch(r"/assets/douban-[\w\-]+\.js", path):
        target_url = f"{TARGET_SERVICE}{path}?{query}" if query else f"{TARGET_SERVICE}{path}"
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            headers = dict(request.headers)
            headers.pop("host", None)
            resp = await client.get(target_url, headers=headers)
            js_code = resp.text
            # 用正则找到 const t = [ ... ];，在数组末尾插入新项
            import re as _re
            match = _re.search(
                r"(const\s+t\s*=\s*\[)(.*?)(\]\s*;\s*export\s*\{\s*t\s+as\s+d\s*\}\s*;?)",
                js_code,
                _re.DOTALL | _re.IGNORECASE
            )
            if match:
                arr_start, arr_body, arr_end = match.groups()
                # 插入新项，注意逗号处理
                arr_body = arr_body.rstrip()
                if not arr_body.endswith(",") and arr_body.strip():
                    arr_body += ","
                arr_body += '''
    {
        type: "tv_animation",
        category: "bangumi",
        api: "tv",
        title: "Bangumi"
    }'''
                new_js = f"{arr_start}{arr_body}{arr_end}"
                print(new_js)
                return Response(content=new_js, media_type="application/javascript")
            # 若未匹配到，原样返回
            return Response(content=js_code, media_type="application/javascript")

    if any(path.startswith(p) for p in INTERCEPT_PATHS):
        # 从查询参数获取keyword
        import urllib.parse
        query_params = dict(request.query_params)
        keyword = query_params.get("keyword", "")
        # keyword以#结尾时，原始请求keyword也去除#
        if keyword and keyword.endswith("#"):
            query_params["keyword"] = keyword[:-1]
            query = urllib.parse.urlencode(query_params)
        # 并发获取原始数据和外部数据
        target_url = f"{TARGET_SERVICE}{path}?{query}" if query else f"{TARGET_SERVICE}{path}"

        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            # 复制请求头
            headers = dict(request.headers)
            headers.pop("host", None)

            # 并发执行
            original_task = client.get(target_url, headers=headers) if request.method == "GET" else \
                client.post(target_url, content=await request.body(), headers=headers)
            # 根据keyword决定是否获取外部数据
            tasks = [original_task]
            if keyword and keyword.endswith("#"):
                tasks.append(fetch_external_data(keyword[:-1], True))
            else:
                tasks.append(fetch_external_data(keyword[:-1]))
            

            results = await asyncio.gather(*tasks)
            original_response = results[0]
            external_data = results[1] if len(results) > 1 else []

            # 处理原始响应
            try:
                original_data = original_response.json()
            except:
                original_data = {"data": []}

            # 合并数据
            if "data" not in original_data:
                original_data["data"] = []

            if external_data:
                for data in external_data:
                    if data != []:  # 确保数据非空
                        original_data["data"].append(data)

            return JSONResponse(original_data, status_code=200)

    # 正常代理流程
    target_url = f"{TARGET_SERVICE}{path}?{query}" if query else f"{TARGET_SERVICE}{path}"

    # 转发请求
    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        # 复制原始请求头
        headers = dict(request.headers)
        headers.pop("host", None)

        # 根据请求方法转发
        if request.method == "GET":
            response = await client.get(target_url, headers=headers)
        elif request.method == "POST":
            body = await request.body()
            response = await client.post(target_url, content=body, headers=headers)
        else:
            return JSONResponse(
                {"error": "Method not supported"},
                status_code=405
            )

    # 返回响应
    headers = dict(response.headers)
    if "content-length" in headers:
        del headers["content-length"]

    try:
        content = response.json()
        return JSONResponse(
            content=content,
            status_code=response.status_code,
            headers=headers
        )
    except ValueError:
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=headers,
            media_type=response.headers.get("content-type")
        )


@app.get("/")
async def root():
    return {"message": "Proxy Server Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config["server"]["host"],
                port=config["server"]["port"], access_log=False)
