FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 测试工具（pytest）与冒烟脚本依赖（requests）一并装入同一镜像，
# 供一次性退出的 verify 服务复用。
COPY requirements-dev.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY tests ./tests
COPY scripts ./scripts

EXPOSE 8000

# api 服务的唯一长驻进程。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
