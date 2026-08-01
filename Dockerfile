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

COPY trade_logger.py .
COPY shadow_forward_tester.py .
COPY leaderboard_writer.py .
COPY bot_output.py .
COPY live_strategy_runner.py .
COPY quote_source.py .
COPY supervisor.py .
COPY refresh_eligible_symbols.py .

COPY strategies /app/strategies
COPY reporting /app/reporting
COPY schwab_bot_dashboard /app/schwab_bot_dashboard

CMD ["python", "-u", "supervisor.py"]
