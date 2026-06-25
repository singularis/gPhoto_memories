FROM python:3.9-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y \
    vim \
    curl \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 5000

# 2 workers = enough for 2 users; --log-level warning keeps the pod quiet
# sync worker is fine — image resize is CPU-bound not I/O-bound
CMD ["gunicorn", \
     "--workers", "2", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--log-level", "warning", \
     "--access-logfile", "-", \
     "app:app"]
