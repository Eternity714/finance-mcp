# 使用官方的 Python 3.11 slim 版本作为基础镜像（多架构支持）
# slim 版本比较小,适合生产环境
# 支持 linux/arm64 (Mac M1/M2) 和 linux/amd64 (Intel/AMD)
FROM python:3.11-slim

# 设置工作目录为 /app
WORKDIR /app

# 配置国内镜像源加速
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（使用国内镜像源）
# 添加 gcc, g++, make 用于编译某些 Python 包（如 lxml, pandas 等）
# 添加 dnsutils, iputils-ping 用于网络调试
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gcc \
    g++ \
    make \
    libxml2-dev \
    libxslt-dev \
    dnsutils \
    iputils-ping \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    PYTHONPATH=/app \
    HOME=/root

# 创建必要的目录（确保 Tushare 等库可以保存文件）
RUN mkdir -p /root/.tushare /root/.akshare /app/logs /app/data && \
    chmod -R 777 /root /app/logs /app/data

# 复制依赖文件 requirements.txt 到工作目录
COPY requirements.txt .

# 使用 pip 安装依赖，使用清华镜像源加速
RUN pip install --no-cache-dir --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 将当前目录下的所有文件（已通过 .dockerignore 过滤）复制到工作目录 /app
COPY . .

# 声明容器对外暴露的端口
# 9998: FastAPI Web 服务器
# 9999: MCP 服务器
EXPOSE 9998 9999

# 添加健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:9998/health || exit 1

# 容器启动时执行的命令
# 使用 main.py 统一启动脚本，同时启动 FastAPI 和 MCP 服务器
CMD ["python", "main.py", \
    "--mcp-mode", "streamable-http", \
    "--http-port", "9998", \
    "--mcp-port", "9999", \
    "--log-level", "INFO"]

