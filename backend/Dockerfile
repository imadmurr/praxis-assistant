# syntax=docker/dockerfile:1
# Stage 1: install dependencies on a slim Python image
FROM python:3.11-slim AS base
# set workdir
WORKDIR /app
# install system packages (optional: build tools, but keep to a minimum)
RUN apt-get update && apt-get install -y --no-install-recommends \
gcc g++ \
&& rm -rf /var/lib/apt/lists/*
# copy requirements file and install deps
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# copy application code
COPY backend .
# use a non-root user for security
RUN useradd -ms /bin/bash appuser
USER appuser
# environment variables (these will be overridden by Render)
ENV PYTHONUNBUFFERED=1 \
FLASK_ENV=production \
PORT=5000
# expose port 5000 for the Flask app
EXPOSE 5000
# default command (use gunicorn in production for better performance)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT app:app --workers 1 --threads 2 --worker-class gthread --timeout 120 --max-requests 50 --max-requests-jitter 10"]