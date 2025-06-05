FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy build dependencies first for better caching
COPY pyproject.toml .
COPY setup.py .

# Install Poetry
RUN pip install poetry==1.6.1

# Configure Poetry to not create virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only=main --no-dev

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p logs configs

# Set Python path
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "-m", "on1builder", "run"]
