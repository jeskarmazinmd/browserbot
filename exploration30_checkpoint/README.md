# Explore30 prospective cohort

Thirty bounded, self-contained, paper-only strategy experiments with a forward
start of 2026-08-10 13:30 UTC. Runtime strategy code shares only the bot's
market-event interface and `EventStrategy` base; it does not consume other
strategy outputs or shared strategic calculators.

## Single-position experiments (22)

- Shock/reversal: SHOCKR1, SHOCKR2, PREVR1, PREVR2, VOLR1, VOLR2
- Trend/acceleration/pullback: TRENDX1, TRENDX2, ACCEL1, ACCEL2, PULLCONT1, PULLCONT2
- Breakout/compression: BRK20, BRK30, COMPX1, COMPX2
- Breadth/context: BREADTH1, BREADTH2
- Session timing: OPENMOM1, MIDREV1, CLOSEMOM1
- Directional entropy: ENTROPY1

## Coordinated multi-leg experiments (8)

- PAIRMR2: dynamic correlated-pair mean reversion
- PAIRTR1: dynamic relative-strength pair continuation
- INVPAIR1: inverse-correlation anomaly
- LEADBASK2: leader/follower lag basket
- PEERBASK1: same-direction peer basket
- MKTNEUT1: long/short market-neutral tech spread
- SECTORROT1: strongest/weakest sector spread
- XASSETPAIR1: cross-asset ETF-proxy relative-value pair

All modules retain at most 66 observations for a fixed universe of at most 32
symbols. ETF proxies (including TLT, GLD, SLV, and USO) are experiments on the
existing equity/ETF data path; they are not futures or commodity contracts.
