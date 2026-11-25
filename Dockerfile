# Backend v0 + v1 (FastAPI). Code sinh viên KHÔNG chạy trong image này: backend gọi Docker của máy
# chủ (qua docker.sock) để chạy từng lệnh trong image kt-sandbox (sandbox/Dockerfile).
FROM docker:27-cli AS dockercli

FROM python:3.10-slim
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY frontend frontend
COPY knowledge knowledge
COPY data/problems data/problems
EXPOSE 8000
# Nạp tri thức tĩnh vào Neo4j (idempotent) rồi chạy API; Neo4j lỗi thì vẫn chạy bằng YAML dự phòng
CMD ["sh", "-c", "python -m backend.app.kg.load --quiet || echo 'Không nạp được KG, dùng YAML dự phòng'; exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
