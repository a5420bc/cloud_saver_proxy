# 云盘搜索代理服务

一个支持多源云盘搜索的代理服务，整合爱盘、云搜等资源。

## 功能特性
- 支持爱盘(1-8个数据源)搜索
- 支持云搜搜索
- 支持Playwright渲染搜索
- 标准化API返回格式
- 自动过滤无效资源
- 资源名称智能清理

## 安装
```bash
pip install -r requirements.txt

# 如需使用Playwright
playwright install
```

## 配置
编辑`src/main.py`配置：
- `TARGET_SERVICE`: 目标服务URL
- `INTERCEPT_PATHS`: 拦截路径列表
- 各搜索源的启用状态

## API接口
### 搜索接口
`GET /api/search?keyword={关键词}`

返回格式：
```json
{
  "list": [{
    "title": "资源名称",
    "cloudLinks": [{
      "link": "网盘链接",
      "cloudType": "quark|tianyi|aliyun",
      "password": "提取码"
    }],
    // 其他元数据
  }]
}
```

## 开发
```bash
# 启动服务
uvicorn src.main:app --reload

# 运行测试
pytest tests/
```

## 部署
推荐使用Docker部署：
```bash
docker build -t cloud-proxy .
docker run -d -p 8000:8000 cloud-proxy