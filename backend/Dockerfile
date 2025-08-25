# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Help pip on slow networks / large wheels (SciPy/Numpy)
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

WORKDIR /app

# Install Python deps first to maximize layer cache
COPY backend/requirements.txt requirements.txt
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir --timeout 180 --retries 10 --prefer-binary -r requirements.txt

# Copy app code
COPY backend .

ENV PORT=5000
EXPOSE 5000
CMD ["gunicorn","--bind","0.0.0.0:5000","app:app","--workers","1","--threads","8","--timeout","120"]
