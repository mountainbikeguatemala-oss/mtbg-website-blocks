FROM python:3.12.7-slim-bookworm
# ffmpeg from Debian 12 (5.1.x): H.264 (libx264), AAC, animated WebP (libwebp), ffprobe
# + Intel media driver (iHD) so the NAS's graphics chip can decode/scale big camera video (VAAPI)
RUN apt-get update \
 && apt-get install -y --no-install-recommends "ffmpeg=7:5.1.*" intel-media-va-driver \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pillow==11.0.0 pillow-heif==0.20.0 requests==2.32.3 tzdata==2024.2
ENV LIBVA_DRIVER_NAME=iHD
WORKDIR /app
COPY *.py /app/
ENTRYPOINT ["python3", "-u"]
