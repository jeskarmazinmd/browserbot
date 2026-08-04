# Paper-only SPY strategy family

Forward testing begins on 2026-08-05. All modules emit SPY signals through the
existing completed-minute pipeline and use the shared paper outcome tracker.
No module places live orders.

## Active modules

| ID | Entry hypothesis | Target | Stop |
| --- | --- | ---: | ---: |
| SPY_OR5 | Break above the 09:30-09:35 ET range by 0.03% | 0.40% | 0.25% |
| SPY_OR15 | Break above the 09:30-09:45 ET range by 0.05% | 0.50% | 0.30% |
| SPY_OR30 | Break above the 09:30-10:00 ET range by 0.07% | 0.60% | 0.35% |
| SPY_MOM1 | 5m return >= 0.08% and 15m return >= 0.15% | 0.45% | 0.30% |
| SPY_MR1 | At least 0.30% below the 20m price mean, then a 0.05% 2m rebound | 0.35% | 0.30% |
| SPY_BR1 | SPY 5m momentum confirmed by at least 58% advancing 5m breadth | 0.45% | 0.30% |
| SPY_XA1 | SPY momentum confirmed by QQQ, IWM, HYG/LQD, and UUP | 0.45% | 0.30% |
| SPY_ENS1 | At least four of six momentum, breadth, and cross-asset votes | 0.50% | 0.30% |

The existing tracker also closes unresolved positions at the configured EOD
exit time. The runner's 30-minute independent-strategy cooldown limits repeat
entries from one module.

## Deferred until their source data is real

- Overnight gap continuation/fade and previous-day effects need a durable prior
  close/open reference.
- True VWAP and opening-volume strategies need completed-minute volume.
- ES futures, foreign-market, VIX, scheduled-event, options-skew, and dealer-
  gamma strategies need validated additional feeds.

Do not substitute rolling price means for VWAP or ETF proxies for unavailable
data without giving the resulting strategy a distinct research hypothesis.
