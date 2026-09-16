"""Install direct registry wiring for the independent orthogonal cohort."""

from pathlib import Path


p = Path("strategies/registry.py")
s = p.read_text()

anchor = '    ("strategy_td1", "TD1Strategy"),\n'
addition = (
    anchor
    + '    ("strategy_qtd1x", "QTD1XStrategy"),\n'
    + '    ("strategy_ptd1x", "PTD1XStrategy"),\n'
    + '    ("strategy_gtmx", "GTMXStrategy"),\n'
)

if '("strategy_qtd1x", "QTD1XStrategy")' not in s:
    if anchor not in s:
        raise SystemExit("minute registry anchor missing")
    s = s.replace(anchor, addition, 1)

p.write_text(s)
print("UPDATED", p)
