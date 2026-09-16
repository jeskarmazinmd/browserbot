"""Install the prospective self-contained multi-leg research family."""

from pathlib import Path
import shutil


ROOT = Path(".").resolve()
SOURCE = Path(__file__).resolve().parent / "multi_leg_checkpoint"

FILES = {
    SOURCE / "multi_leg_paper_tracker.py": ROOT / "multi_leg_paper_tracker.py",
    SOURCE / "strategies/strategy_pairmr1.py": ROOT / "strategies/strategy_pairmr1.py",
    SOURCE / "strategies/strategy_leadbask1.py": ROOT / "strategies/strategy_leadbask1.py",
    SOURCE / "strategies/strategy_sectorh1.py": ROOT / "strategies/strategy_sectorh1.py",
    SOURCE / "tests/test_multi_leg_paper_tracker.py": ROOT / "tests/test_multi_leg_paper_tracker.py",
    SOURCE / "tests/test_multi_leg_strategies.py": ROOT / "tests/test_multi_leg_strategies.py",
}

for source, target in FILES.items():
    if not source.exists():
        raise SystemExit(f"missing checkpoint file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


registry = ROOT / "strategies/registry.py"
s = registry.read_text()
anchor = '    ("strategy_gtmx", "GTMXStrategy"),\n'
addition = (
    '    ("strategy_pairmr1", "PAIRMR1Strategy"),\n'
    '    ("strategy_leadbask1", "LEADBASK1Strategy"),\n'
    '    ("strategy_sectorh1", "SECTORH1Strategy"),\n'
)
if "strategy_pairmr1" not in s:
    if anchor not in s:
        raise SystemExit("registry anchor missing")
    s = s.replace(anchor, anchor + addition, 1)
    registry.write_text(s)


runner = ROOT / "live_strategy_runner.py"
s = runner.read_text()
import_anchor = "from paper_outcome_tracker import PaperOutcomeTracker\n"
if "from multi_leg_paper_tracker import MultiLegPaperTracker" not in s:
    if import_anchor not in s:
        raise SystemExit("runner import anchor missing")
    s = s.replace(import_anchor, import_anchor + "from multi_leg_paper_tracker import MultiLegPaperTracker\n", 1)

tracker_anchor = '''    print(
        "PAPER_OUTCOME_TRACKER_ONLINE "
        f"active={len(paper_outcomes.active)} seen={len(paper_outcomes.seen)}",
        flush=True,
    )
'''
tracker_addition = '''    multi_leg_outcomes = MultiLegPaperTracker(
        DATA_ROOT,
        eod_hour=EOD_EXIT_HOUR_ET,
        eod_minute=EOD_EXIT_MINUTE_ET,
    )
    print(
        "MULTI_LEG_PAPER_TRACKER_ONLINE "
        f"active={len(multi_leg_outcomes.active)} seen={len(multi_leg_outcomes.seen)}",
        flush=True,
    )
'''
if "MULTI_LEG_PAPER_TRACKER_ONLINE" not in s:
    if tracker_anchor not in s:
        raise SystemExit("runner tracker initialization anchor missing")
    s = s.replace(tracker_anchor, tracker_anchor + tracker_addition, 1)

update_anchor = '''            for outcome in paper_outcomes.update(prices_now, now_utc):
                print(
                    "PAPER_OUTCOME "
                    f"strategy={outcome['strategy_id']} symbol={outcome['symbol']} "
                    f"reason={outcome['exit_reason']} pnl={outcome['pnl']:+.2f}",
                    flush=True,
                )
'''
update_addition = '''            for outcome in multi_leg_outcomes.update(prices_now, now_utc):
                print(
                    "MULTI_LEG_PAPER_OUTCOME "
                    f"strategy={outcome['strategy_id']} group={outcome['group_id']} "
                    f"reason={outcome['exit_reason']} pnl={outcome['pnl']:+.2f}",
                    flush=True,
                )
'''
if "MULTI_LEG_PAPER_OUTCOME " not in s:
    if update_anchor not in s:
        raise SystemExit("runner outcome update anchor missing")
    s = s.replace(update_anchor, update_anchor + update_addition, 1)

minute_anchor = '''                minute_payloads = apply_capacity_filters([
                    snapshot_signal_payload(signal)
                    for signal in minute_signals
                ])
'''
minute_replacement = '''                multi_leg_signals = [
                    signal
                    for signal in minute_signals
                    if signal.signal_type == "MULTI_LEG"
                ]
                single_leg_signals = [
                    signal
                    for signal in minute_signals
                    if signal.signal_type != "MULTI_LEG"
                ]

                for signal in multi_leg_signals:
                    multi_payload = {
                        "strategy_id": str(signal.strategy_id),
                        "timestamp": pd.Timestamp(signal.timestamp).isoformat(),
                        **dict(signal.data or {}),
                    }
                    if multi_leg_outcomes.register(multi_payload):
                        append_strategy_event(
                            str(signal.strategy_id),
                            "MULTI_LEG_SIGNAL",
                            group=multi_payload,
                            signal_regime=latest_regime(),
                            thresholds={
                                "LIVE_ORDER_PLACEMENT": False,
                                "CADENCE": "minute",
                                "ACCOUNTING": "coordinated_group",
                            },
                        )

                minute_payloads = apply_capacity_filters([
                    snapshot_signal_payload(signal)
                    for signal in single_leg_signals
                ])
'''
if "multi_leg_signals = [" not in s:
    if minute_anchor not in s:
        raise SystemExit("runner minute routing anchor missing")
    s = s.replace(minute_anchor, minute_replacement, 1)

runner.write_text(s)


dockerfile = ROOT / "Dockerfile"
s = dockerfile.read_text()
docker_anchor = "COPY paper_outcome_tracker.py .\n"
docker_line = "COPY multi_leg_paper_tracker.py .\n"
if docker_line not in s:
    if docker_anchor not in s:
        raise SystemExit("Dockerfile paper tracker anchor missing")
    s = s.replace(docker_anchor, docker_anchor + docker_line, 1)
    dockerfile.write_text(s)

print("INSTALLED prospective multi-leg paper family: PAIRMR1 LEADBASK1 SECTORH1")
