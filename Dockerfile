FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
COPY pyproject.toml .
COPY setup.py .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -e .

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p logs configs

# Set Python path
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "ignition.py"]
