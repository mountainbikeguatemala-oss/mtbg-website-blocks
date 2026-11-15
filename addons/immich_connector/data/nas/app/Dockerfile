FROM python:3.12.7-slim
RUN pip install --no-cache-dir pillow==11.0.0 pillow-heif==0.20.0 requests==2.32.3 tzdata==2024.2
WORKDIR /app
COPY *.py /app/
ENTRYPOINT ["python3", "-u"]
