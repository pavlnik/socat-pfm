FROM python:3.11-alpine

LABEL org.opencontainers.image.source="https://github.com/pavlnik/socat-web"
LABEL description="Socat Web - Lightweight Port Forwarding Interface"

RUN apk add --no-cache socat bash

WORKDIR /app

RUN pip install --no-cache-dir Flask 

COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN mkdir -p /app/backend/data

ENV PORT=5000
ENV PYTHONUNBUFFERED=1

EXPOSE $PORT

CMD ["python", "backend/app.py"]