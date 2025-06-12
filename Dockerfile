# ---------- 基础镜像 ----------
FROM python:3.11-slim

# ---------- 装系统依赖 ----------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxrandr2 libgbm1 libpango1.0-0 libcups2 \
        libgtk-3-0 wget gnupg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# ---------- 复制代码 ----------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

# ---------- 启动 ----------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
