import asyncio
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import httpx
from httpx import Timeout

# 更长的全局超时设置(300秒=5分钟)
HTTPX_TIMEOUT = 60
from index.api.yunso import YunsoSearch
from index.api.aipan import AipanSearch

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    # app.state.panyq_search = PanyqSearch()
    app.state.yunso_search = YunsoSearch()
    # 初始化1-8个aipan实例
    app.state.aipan_searches = [AipanSearch(source_id=i) for i in range(1, 9)]
    # if app.state.panyq_search.use_playwright:
    #     await app.state.panyq_search._async_init()
    
    yield
    
    # 关闭时清理
    # await app.state.panyq_search.close()

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
    # 并发执行搜索
    # 并发执行所有搜索
    yunso_data, panyq_data, *aipan_data = await asyncio.gather(
        asyncio.to_thread(app.state.yunso_search.search, keyword),
        # app.state.panyq_search.search(keyword),
        *[asyncio.to_thread(search.search, keyword) for search in app.state.aipan_searches]
    )

    # 合并结果
    results = []
    if yunso_data and yunso_data.get("list"):
        results.append(yunso_data)
    if panyq_data and panyq_data.get("list"):
        results.append(panyq_data)
    # 添加所有aipan结果
    for data in aipan_data:
        if data and data.get("list"):
            results.append(data)

    return results


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
