# Use an official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (for uvicorn, websockets, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirement files if you have them
COPY requirements.txt .

# Install Python dependencies (fallback to pip freeze if no file)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt || true

# Copy the rest of the source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Use Uvicorn to serve FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]