# AuctionRouter — single Hugging Face Docker Space
# Stage 1: build the Next.js frontend as a static export (next.config: output "export")
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI serves the API and the built frontend on port 7860
FROM python:3.12-slim
WORKDIR /app

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir uv \
    && uv pip install --system -r pyproject.toml

COPY backend/app ./app
COPY --from=frontend /frontend/out ./static

# HF Spaces runs containers as UID 1000
RUN useradd -m -u 1000 user && chown -R user /app
USER user

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
