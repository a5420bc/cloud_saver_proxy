# 基于官方 Python 3.11 精简版镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目源码
COPY . .

# 默认启动命令（可根据实际情况修改）
CMD ["python", "src/main.py"]