FROM python:3.12-slim
RUN pip install --no-cache-dir boto3==1.44.0
WORKDIR /app
COPY pairs.py .
STOPSIGNAL SIGINT
ENTRYPOINT ["python", "pairs.py"]
