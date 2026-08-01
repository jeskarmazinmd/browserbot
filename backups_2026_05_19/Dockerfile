FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY trendline_scanner_v22.py .
COPY 1Mvolumesymbols.csv .
COPY schwab_token.json .

CMD ["python", "-u", "trendline_scanner_v22.py"]
