FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GOTES_DATA_DIR=/app/.data \
    GOTES_MEDIA_ROOT=/app/.data/media

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x /app/docker-entrypoint.sh /app/docker-entrypoint.prod.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
