FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 RUN_MODE=LIVE C3_ONLY=1 LIVE_ORDER_PLACEMENT_ENABLED=0
CMD ["python", "-u", "c3_supervisor.py"]
