FROM python:3.9-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y \
    vim \
    curl

EXPOSE 5000

CMD ["python", "app.py"]
