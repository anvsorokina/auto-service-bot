FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Expose port
EXPOSE 8000

# Run on port 8000 (default)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
