# Fast Dockerfile - uses Node base image
FROM node:20-slim AS frontend-builder

# Build frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Python backend
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy backend
COPY backend ./backend

# Start server
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT"]