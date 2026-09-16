# Build context is the REPO ROOT (parent of backend/ and frontend/) — both are needed
# since the backend serves the frontend's build output from a sibling directory
# (main.py's FRONTEND_DIST_DIR = <repo>/frontend/dist).
# Build from the repo root:  docker build -t migration-tool:latest .

# ---------- Stage 1: build the React frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: backend runtime ----------
FROM python:3.11-slim AS backend
WORKDIR /app

# psycopg2-binary ships a prebuilt wheel, so no build-essential/libpq-dev needed.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend-build /build/frontend/dist frontend/dist

# Uploaded CSVs, Parquet copies, and validation results live under storage/ (see
# backend/utils/storage_paths.py, APP_STORAGE_ROOT) — mount a volume here in
# docker-compose so they survive container restarts/rebuilds. Can grow large (multi-GB
# source files + their Parquet copies), so give the host disk enough headroom.
RUN mkdir -p storage

WORKDIR /app/backend
EXPOSE 8060

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060"]
