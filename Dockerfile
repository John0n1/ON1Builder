FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy build dependencies first for better caching
COPY pyproject.toml .

# Install dependencies using pip and pyproject.toml
RUN pip install --no-cache-dir .

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p logs configs

# Set Python path
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "-m", "on1builder", "run"]
