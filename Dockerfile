FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY trendline_scanner_v25_live_schwab.py .
COPY live_quote_collector.py .
COPY 1Mvolumesymbols.csv .

COPY schwab_clients.py .
COPY reauth_market.py .
COPY reauth_trade.py .

COPY trade_logger.py .
COPY leaderboard_writer.py .
COPY bot_output.py .
COPY bounded_jsonl.py .
COPY live_strategy_runner.py .
COPY paper_outcome_tracker.py .
COPY multi_leg_paper_tracker.py .
COPY strategy_diagnostics.py .
COPY strategy_diagnostics_report.py .
COPY quote_source.py .
COPY market_quotes.py .
COPY market_evidence.py .
COPY xs_shadow_worker.py .
COPY options_shadow_worker.py .
COPY options_paper_tracker.py .
COPY futures_shadow_worker.py .
COPY futures_paper_tracker.py .
COPY forex_shadow_worker.py .
COPY forex_paper_tracker.py .
COPY schwab_token_guard.py .
COPY supervisor.py .
COPY data_maintenance.py .
COPY refresh_eligible_symbols.py .
COPY universe_tags.py .
COPY regime_detector.py .
COPY regime_logger.py .

COPY engine /app/engine
COPY strategies /app/strategies
COPY options_strategies /app/options_strategies
COPY futures_strategies /app/futures_strategies
COPY forex_strategies /app/forex_strategies
COPY detectors /app/detectors
COPY reporting /app/reporting
COPY research_lab /app/research_lab
COPY schwab_bot_dashboard /app/schwab_bot_dashboard

CMD ["python", "-u", "supervisor.py"]
