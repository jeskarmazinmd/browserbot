from pathlib import Path
import re
import shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
p=ROOT/"live_strategy_runner.py";s=p.read_text()
old='def explicit_refresh_schwab_token(token_path, app_key, app_secret):\n    import base64\n    import requests\n\n    path = Path(token_path)\n    status_path = DATA_ROOT / "trading_auth_status.json"'
new='def explicit_refresh_schwab_token(token_path, app_key, app_secret, status_path=None):\n    import base64\n    import requests\n\n    path = Path(token_path)\n    status_path = Path(status_path) if status_path is not None else DATA_ROOT / "trading_auth_status.json"'
if old in s:s=s.replace(old,new,1)
elif new not in s:raise SystemExit("explicit refresh signature anchor missing")
marker='\nVOLUME_METRIC_KEYS = ('
helper='''

AUTH_EVENTS_PATH = DATA_ROOT / "auth_events.jsonl"
AUTH_EVENTS_MAX_ROWS = 2000
TOKEN_REFRESH_THRESHOLD_MINUTES = 20.0
TOKEN_REFRESH_VERIFY_MINUTES = 25.0


def record_auth_event(kind, **fields):
    """Persist bounded, token-free authentication evidence."""
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": kind, **fields}
    AUTH_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUTH_EVENTS_PATH.open("a") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\\n")
    try:
        lines = AUTH_EVENTS_PATH.read_text().splitlines()
        if len(lines) > AUTH_EVENTS_MAX_ROWS:
            atomic_write_json(DATA_ROOT / "auth_events_compaction_status.json", {"timestamp": row["timestamp"], "rows_before": len(lines), "rows_after": AUTH_EVENTS_MAX_ROWS})
            tmp = AUTH_EVENTS_PATH.with_suffix(".tmp")
            tmp.write_text("\\n".join(lines[-AUTH_EVENTS_MAX_ROWS:]) + "\\n")
            os.replace(tmp, AUTH_EVENTS_PATH)
    except Exception:
        pass
'''
if "AUTH_EVENTS_PATH =" not in s:
    if marker not in s:raise SystemExit("auth helper insertion anchor missing")
    s=s.replace(marker,helper+marker,1)
old='''            if market_min_left < 20 and now_ts - last_market_token_touch >= 60:
                last_market_token_touch = now_ts
                try:
                    from schwab.auth import client_from_token_file
                    market_client = client_from_token_file(
                        market_token_path,
                        os.environ["SCHWAB_MARKET_APP_KEY"],
                        os.environ["SCHWAB_MARKET_SECRET"],
                    )
                    r = market_client.get_quotes(["VOO"])
                    print(f"MARKET_TOKEN_REFRESH status={getattr(r, 'status_code', 'NA')} before_min_left={market_min_left:.1f}", flush=True)
                except Exception as e:
                    print(f"MARKET_TOKEN_REFRESH error: {type(e).__name__}: {e}", flush=True)
'''
new='''            if market_min_left < TOKEN_REFRESH_THRESHOLD_MINUTES and now_ts - last_market_token_touch >= 60:
                last_market_token_touch = now_ts
                try:
                    from schwab.auth import client_from_token_file
                    after_min_left = explicit_refresh_schwab_token(
                        market_token_path,
                        os.environ["SCHWAB_MARKET_APP_KEY"],
                        os.environ["SCHWAB_MARKET_SECRET"],
                        DATA_ROOT / "market_auth_status.json",
                    )
                    if after_min_left < TOKEN_REFRESH_VERIFY_MINUTES:
                        raise RuntimeError(f"persisted market token lifetime too short: {after_min_left:.1f} minutes")
                    market_client = client_from_token_file(
                        market_token_path,
                        os.environ["SCHWAB_MARKET_APP_KEY"],
                        os.environ["SCHWAB_MARKET_SECRET"],
                    )
                    r = market_client.get_quotes(["VOO"])
                    status_code = getattr(r, "status_code", None)
                    if status_code != 200:
                        raise RuntimeError(f"post-refresh market verification status={status_code}")
                    record_auth_event("market_refresh_ok", before_min_left=round(market_min_left, 3), after_min_left=round(after_min_left, 3), verification_status=status_code)
                    print(f"MARKET_TOKEN_REFRESH OK before_min_left={market_min_left:.1f} after_min_left={after_min_left:.1f} verification_status={status_code}", flush=True)
                except Exception as e:
                    record_auth_event("market_refresh_error", before_min_left=round(market_min_left, 3), error_type=type(e).__name__, error=str(e)[:500])
                    print(f"MARKET_TOKEN_REFRESH error: {type(e).__name__}: {e}", flush=True)
'''
if old in s:s=s.replace(old,new,1)
elif 'record_auth_event("market_refresh_ok"' not in s:
    pattern=r'                if market_min_left < 20 and now_ts - last_market_token_touch >= 60:\n.*?(?=\n                trade_token_path = "/data/schwab_trade_token.json")'
    indented_new="\n".join(("    "+line if line else line) for line in new.rstrip("\n").splitlines())
    s,count=re.subn(pattern,indented_new,s,count=1,flags=re.DOTALL)
    if count!=1:raise SystemExit("market refresh block anchor missing")
old='''                try:
                    after_min_left = explicit_refresh_schwab_token(
                        trade_token_path,
                        os.environ["SCHWAB_TRADING_APP_KEY"],
                        os.environ["SCHWAB_TRADING_SECRET"],
                    )
                    refreshed = make_trader()
                    trader = refreshed
                    print(f"TRADING_TOKEN_REFRESH OK before_min_left={trade_min_left:.1f} after_min_left={after_min_left:.1f}", flush=True)
                except Exception as e:
                    print(f"TRADING_TOKEN_REFRESH error: {type(e).__name__}: {e}", flush=True)
'''
new='''                try:
                    after_min_left = explicit_refresh_schwab_token(
                        trade_token_path,
                        os.environ["SCHWAB_TRADING_APP_KEY"],
                        os.environ["SCHWAB_TRADING_SECRET"],
                        DATA_ROOT / "trading_auth_status.json",
                    )
                    if after_min_left < TOKEN_REFRESH_VERIFY_MINUTES:
                        raise RuntimeError(f"persisted trading token lifetime too short: {after_min_left:.1f} minutes")
                    refreshed = make_trader()
                    if not bool(getattr(refreshed, "enabled", True)):
                        raise RuntimeError("post-refresh trading account verification failed")
                    trader = refreshed
                    record_auth_event("trading_refresh_ok", before_min_left=round(trade_min_left, 3), after_min_left=round(after_min_left, 3), account_verification="enabled")
                    print(f"TRADING_TOKEN_REFRESH OK before_min_left={trade_min_left:.1f} after_min_left={after_min_left:.1f} account_verification=enabled", flush=True)
                except Exception as e:
                    record_auth_event("trading_refresh_error", before_min_left=round(trade_min_left, 3), error_type=type(e).__name__, error=str(e)[:500])
                    print(f"TRADING_TOKEN_REFRESH error: {type(e).__name__}: {e}", flush=True)
'''
if old in s:s=s.replace(old,new,1)
elif 'record_auth_event("trading_refresh_ok"' not in s:
    pattern=r'                    try:\n                        after_min_left = explicit_refresh_schwab_token\(\n                            trade_token_path,.*?                        print\(f"TRADING_TOKEN_REFRESH error: \{type\(e\)\.__name__\}: \{e\}", flush=True\)\n'
    indented_new="\n".join(("    "+line if line else line) for line in new.rstrip("\n").splitlines())+"\n"
    s,count=re.subn(pattern,indented_new,s,count=1,flags=re.DOTALL)
    if count!=1:raise SystemExit("trading refresh block anchor missing")
p.write_text(s)
scanner=ROOT/"trendline_scanner_v25_live_schwab.py";s=scanner.read_text();old='print(f"market token low ({mins:.1f} min left); rebuilding Schwab client proactively", flush=True)';new='print(f"market token below owner threshold ({mins:.1f} min left); strategy runner owns explicit refresh", flush=True)'
if old in s:s=s.replace(old,new,1)
elif new not in s:raise SystemExit("collector token message anchor missing")
scanner.write_text(s)
(ROOT/"tests").mkdir(exist_ok=True);shutil.copy2(HERE/"tests/test_market_token_reliability.py",ROOT/"tests/test_market_token_reliability.py")
print("INSTALLED verified proactive market-token refresh")
