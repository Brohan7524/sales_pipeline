FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY datasets/ ./datasets/

CMD ["python", "scripts/run_pipeline.py"]
