FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2 and curl (for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["gunicorn", "main:app", "-c", "gunicorn.conf.py"]
