# Container build for Hugging Face Spaces, Fly.io, Railway, or any Docker host.
#
# Hugging Face Spaces expects port 7860, which is what this listens on. For other
# hosts set PORT and override the command:
#   docker run -p 8000:8000 -e PORT=8000 hookforge \
#     uvicorn app.main:app --host 0.0.0.0 --port 8000
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOOKFORGE_DATA=/app/data \
    HOOKFORGE_MAX_UPLOAD_MB=60 \
    PORT=7860

WORKDIR /app

# No apt-get ffmpeg needed: imageio-ffmpeg ships a static build with libass, which
# is what burns the captions. Verified in development: the same binary reports the
# subtitles filter as available.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

# Build the demo clip at image build time so /api/demo works on a cold container.
RUN python scripts/make_sample_assets.py || echo "sample clip build skipped"

EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
