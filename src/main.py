import asyncio
import json
import importlib
import pkgutil
import yaml
from pathlib import Path
from typing import Dict, Type
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import httpx
from httpx import Timeout
from index.base import BaseSearch

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
        self.search_plugins: Dict[str, Dict] = {}  # {name: {'cls': cls, 'enabled': bool}}
    
    def discover_plugins(self, disabled_plugins: list = None):
        """自动发现api目录下的搜索插件"""
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
                self.plugin_instances[name] = [cls(source_id=i) for i in range(1, 9)]
                app.state.aipan_searches = self.plugin_instances[name]  # 仅aipan需要挂载到app.state
            else:
                self.plugin_instances[name] = cls()

plugin_manager = PluginManager()

from contextlib import asynccontextmanager

# 在模块加载时初始化插件
disabled_plugins = config.get("disabled_plugins", [])
plugin_manager.discover_plugins(disabled_plugins)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 只在应用启动和关闭时触发一次"""
    # 初始化插件实例
    await plugin_manager.init_plugins(app)
    print(f"已初始化插件: {[name for name, p in plugin_manager.search_plugins.items() if p['enabled']]}")
    yield
    # 应用关闭时的清理逻辑可以放在这里

app = FastAPI(lifespan=lifespan)

import yaml
from pathlib import Path

# 加载配置文件
with open(Path(__file__).parent.parent / "config.yaml") as f:
    config = yaml.safe_load(f)

# 服务配置
TARGET_SERVICE = config["target_service"]
INTERCEPT_PATHS = config["intercept_paths"]


async def fetch_external_data(keyword: str):
    """从多个数据源并发获取外部数据"""
    # 准备搜索任务
    search_tasks = []
    
    # 通过plugin_manager获取所有启用的搜索插件实例
    for name, plugin in plugin_manager.search_plugins.items():
        if not plugin['enabled']:
            continue
            
        if name == 'aipan':
            # 特殊处理aipan的多个实例
            search_tasks.extend(
                asyncio.to_thread(search.search, keyword)
                for search in plugin_manager.plugin_instances[name]
            )
            pass
        else:
            search_inst = plugin_manager.plugin_instances.get(name)
            if search_inst:
                search_tasks.append(
                    asyncio.to_thread(search_inst.search, keyword)
                )
    
    # 执行并发搜索
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    
    # 过滤并合并有效结果
    return [
        result for result in search_results
        if not isinstance(result, Exception)
        and result
        and result.get("list")
    ]


@app.middleware("http")
async def proxy_middleware(request: Request, call_next):
    path = request.url.path
    query = str(request.url.query)

    if any(path.startswith(p) for p in INTERCEPT_PATHS):
        # 从查询参数获取keyword
        query_params = dict(request.query_params)
        keyword = query_params.get("keyword", "")

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
            if keyword:
                tasks.append(fetch_external_data(keyword))
            
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
    uvicorn.run(app, host=config["server"]["host"], port=config["server"]["port"])
