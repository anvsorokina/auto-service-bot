FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Expose port (Railway sets PORT env var)
EXPOSE 8000

# Use shell form so $PORT is expanded at runtime
CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
