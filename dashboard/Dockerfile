# Build từ thư mục gốc repo: docker build -f dashboard/Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY dashboard/requirements.txt dashboard/requirements.txt
RUN pip install -r dashboard/requirements.txt
COPY dashboard/ dashboard/
COPY docs/report/ docs/report/
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
