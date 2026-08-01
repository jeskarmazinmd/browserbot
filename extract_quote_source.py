from pathlib import Path

SOURCE = Path("live_strategy_runner.py")
DEST = Path("quote_source_extracted.py")

text = SOURCE.read_text()



globals_to_copy = [
    "_TAPE_CACHE",
    "_TAPE_OFFSET",
    "_TAPE_PARTIAL",
    "_TAPE_PATH",
    "_TAPE_INODE",
    "CACHE_MINUTES",
    "INITIAL_TAIL_ROWS",
]

def find_global(name):
    for i, line in enumerate(lines):
        if line.startswith(name + " ="):
            return line
    raise RuntimeError(f"Couldn't find global {name}")


functions = [
    "_parse_quote_bytes",
    "_to_minute_cache",
    "_merge_minute_cache",
    "_initialise_tape_cache",
    "read_data",
]

lines = text.splitlines()

def find_function(name):
    start = None

    for i, line in enumerate(lines):
        if line.startswith(f"def {name}("):
            start = i
            break

    if start is None:
        raise RuntimeError(f"Couldn't find {name}")

    end = len(lines)

    for i in range(start + 1, len(lines)):
        line = lines[i]
        if (
            line
            and not line.startswith((" ", "\t"))
            and not line.startswith("@")
            and i > start
        ):
            end = i
            break

    return "\n".join(lines[start:end]).rstrip()


out = []
out.append("# Auto-generated from live_strategy_runner.py")
out.append("")
out.append("from pathlib import Path")
out.append("from datetime import datetime, timezone")
out.append("import pandas as pd")
out.append("")

out.append("# Globals")
out.append("")

for g in globals_to_copy:
    print(f"Extracting global {g}")
    out.append(find_global(g))

out.append("")
out.append("# Functions")
out.append("")

for fn in functions:
    print(f"Extracting {fn}")
    out.append(find_function(fn))
    out.append("")

DEST.write_text("\n".join(out))

print()
print(f"Wrote {DEST}")
