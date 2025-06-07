FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p /app/static/pics /app/credentials /app/templates

EXPOSE 5000

CMD ["python", "gphoto_picker.py"]
