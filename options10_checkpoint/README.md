# Options10 prospective paper family

This is a separate options research failure domain. It does not register with
the equity strategy runner and it contains no broker-order path.

- Underlyings: SPY, QQQ, IWM, AAPL, NVDA, TSLA
- Schwab option-chain polling: 120 seconds during regular market hours
- Requested DTE: 7 through 45 days
- Chain strike count: 5
- Evidence: gzip JSONL chain snapshots containing Schwab bid/ask/size,
  volume/open interest, IV, Greeks, strike, expiry and timestamps
- Paper fills: BUY at ask; SELL at bid; closing prices cross the spread again
- Structures: debit-only in this first cohort
- Delayed chains: archived but never allowed to generate a decision
- Forward start: 2026-08-10 13:30 UTC

Strategies:

- OPTDIR1 / OPTDIR2: directional underlying momentum confirmed with liquid ~ATM options
- OPTREV1: underlying reversal
- OPTBRK1: underlying breakout
- OPTIVR1: unusually low own-history IV, long premium only
- OPTSKEW1: put/call IV skew, buying only the relatively cheap wing
- OPTTERM1: near/far IV term-structure dislocation, buying the relatively cheap tenor
- OPTSTRAD1: long ATM straddle after realized underlying movement
- OPTVERT1 / OPTVERT2: defined-risk directional debit verticals

These experiments create prospective evidence. They are not evidence of future
profitability and do not pretend equity history is historical option data.
