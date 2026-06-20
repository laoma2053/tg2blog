FROM python:3.12-slim

WORKDIR /app

# 优先复制依赖文件，利用 Docker 层缓存加速重复构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# 确保数据目录存在（实际内容由 volume 挂载覆盖）
RUN mkdir -p /data/db /data/session /tmp/tg2blog

CMD ["python", "-m", "app.main"]
