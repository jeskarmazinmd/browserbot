# Commodity10 prospective cohort

Ten bounded paper-only commodity/macro ETF experiments using the bot's existing
Schwab equity/ETF snapshot path. No futures or forex contracts are modeled.

- CMDMETMR1: GLD/SLV relative mean reversion
- CMDMETTR1: confirmed precious-metals momentum
- CMDGDR1: gold/rates-proxy relationship (GLD/TLT)
- CMDGDU1: gold/dollar-proxy relationship (GLD/UUP)
- CMDOIL1: crude-oil proxy leading energy equities (USO/XLE)
- CMDGAS1: natural-gas/energy confirmation (UNG/XLE)
- CMDMIN1: gold leading gold miners (GLD/GDX)
- CMDCOP1: copper/mining confirmation (COPX/XME)
- CMDBRD1: broad commodity/proxy breadth
- CMDROT1: strongest positive commodity sleeve rotation

All runtime modules are self-contained apart from the bot's minimal event/base
interfaces, retain at most 61 observations across at most 14 symbols, place no
live orders, and start prospectively at 2026-08-10 13:30 UTC. Missing proxy ETFs
are treated as missing observations rather than failures.
