# gunicorn.conf.py — Production ASGI server configuration
import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WEB_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 8)))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
