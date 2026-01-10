FROM python:3.11-alpine

RUN apk add --no-cache socat bash

WORKDIR /app

RUN pip install --no-cache-dir Flask

COPY backend /app/backend
COPY frontend /app/frontend

RUN mkdir -p /app/data
VOLUME /app/data

ENV PORT=5000

EXPOSE $PORT

CMD ["python", "backend/app.py"]
