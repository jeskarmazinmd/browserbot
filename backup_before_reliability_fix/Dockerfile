FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY trendline_scanner_v22.py .
COPY trendline_scanner_v25_live_schwab.py .
COPY live_quote_collector.py .
COPY 1Mvolumesymbols.csv .

COPY schwab_clients.py .
COPY backfill_45m.py .
COPY reauth_market.py .
COPY reauth_trade.py .
CMD ["python", "-u", "trendline_scanner_v25_live_schwab.py"]

COPY trade_logger.py .
COPY shadow_forward_tester.py .
COPY leaderboard_writer.py .
COPY bot_output.py .
COPY live_strategy_runner.py .

