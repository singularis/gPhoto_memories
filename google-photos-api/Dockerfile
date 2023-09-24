FROM python:3.9-slim

RUN apt-get update && apt-get install -y vim

WORKDIR /app

COPY . /app

RUN mkdir ./media_items_list

RUN pip install --no-cache-dir -r requirements.txt
