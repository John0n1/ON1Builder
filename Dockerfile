FROM python:3.12-slim

LABEL maintainer="ON1Builder Team <info@on1builder.com>"
LABEL version="1.0.0"
LABEL description="ON1Builder - Multi-Chain MEV Trading Bot"

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 on1builder && \
    useradd -u 1000 -g on1builder -s /bin/bash -m on1builder

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set proper ownership
RUN chown -R on1builder:on1builder /app

# Switch to non-root user
USER on1builder

# Create necessary directories with correct permissions
RUN mkdir -p data/logs && \
    mkdir -p data/ml

# Expose the application port
EXPOSE 5001

# Set the entrypoint
ENTRYPOINT ["python"]

# Set default command
CMD ["scripts/python/app_multi_chain.py"] 