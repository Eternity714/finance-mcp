# 使用官方的 Python 3.11 slim 版本作为基础镜像
# slim 版本比较小，适合生产环境
FROM python:3.11-slim

# 设置工作目录为 /app
WORKDIR /app

# 创建非 root 用户用于运行应用
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 配置国内镜像源加速
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（使用国内镜像源）
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 设置环境变量，防止 Python 生成 .pyc 文件和启用无缓冲输出
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_CONFIG=production \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# 复制依赖文件 requirements.txt 到工作目录
COPY requirements.txt .

# 使用 pip 安装依赖，使用清华镜像源加速
RUN pip install --no-cache-dir --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 将当前目录下的所有文件（已通过 .dockerignore 过滤）复制到工作目录 /app
COPY . .

# 设置文件权限
RUN chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 声明容器对外暴露的端口
EXPOSE 5005

# 添加健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5005/api/v1/health || exit 1

# 容器启动时执行的命令
# 使用 gunicorn 提供生产级性能
# --workers: worker 进程数量（建议为 CPU 核心数 * 2 + 1）
# --bind: 绑定地址和端口
# --timeout: 请求超时时间
# --keep-alive: keep-alive 连接超时时间
# --max-requests: 每个 worker 处理的最大请求数（防止内存泄漏）
# --preload: 预加载应用代码（提高性能）
CMD ["gunicorn", \
    "--workers", "4", \
    "--bind", "0.0.0.0:5005", \
    "--timeout", "120", \
    "--keep-alive", "2", \
    "--max-requests", "1000", \
    "--max-requests-jitter", "100", \
    "--preload", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "app:app"]

