FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY samples ./samples

ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# 运行时通过 -e DEEPSEEK_API_KEY=... 传入密钥；data/ 建议挂载为卷以保留数据库
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
