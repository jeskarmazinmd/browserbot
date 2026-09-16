from pathlib import Path


p = Path("strategies/registry.py")
s = p.read_text()

import_anchor = "from . import strategy_c1f1\n"
import_add = (
    "from . import strategy_c1f1\n"
    "from . import strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15\n"
    "from . import strategy_j2t15, strategy_j2mid, strategy_j2rb30\n"
)
if "from . import strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15" not in s:
    if import_anchor not in s:
        raise SystemExit("registry flash import anchor missing")
    s = s.replace(import_anchor, import_add, 1)

tuple_anchor = "        strategy_a, strategy_b, strategy_c1f1, strategy_d, strategy_h,\n"
tuple_add = (
    "        strategy_a, strategy_b, strategy_c1f1, strategy_d, strategy_h,\n"
    "        strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15,\n"
    "        strategy_j2t15, strategy_j2mid, strategy_j2rb30,\n"
)
tuple_marker = "        strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15,\n"
if tuple_marker not in s:
    if tuple_anchor not in s:
        raise SystemExit("registry flash tuple anchor missing")
    s = s.replace(tuple_anchor, tuple_add, 1)

p.write_text(s)
print("REPAIRED", p)
