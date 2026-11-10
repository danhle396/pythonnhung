# Build từ thư mục gốc repo: docker build -f backend/Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
# thư viện mlcore + pipeline (dùng chung code với phần huấn luyện) và model đã huấn luyện
COPY ml/ ml/
RUN pip install -e ml
COPY backend/ backend/
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
