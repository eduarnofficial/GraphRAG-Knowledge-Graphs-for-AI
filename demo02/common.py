"""Small helpers shared by every script in demo02.

Nothing graph-specific lives here - just "read a CSV" and "print a nice table",
so the teaching scripts stay focused on modelling and querying.
"""
import csv
import sys
from pathlib import Path

# Make Windows terminals print arrows and accents correctly.
sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
DATA = HERE / "data"
OUTPUT = HERE / "output"


def read_csv(name, folder=DATA):
    """Return the rows of data/<name>.csv as a list of dicts (column name -> text)."""
    with open(folder / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def banner(title, ch="="):
    print("\n" + ch * 90)
    print(title)
    print(ch * 90)


def print_table(columns, rows):
    """Print rows as a simple aligned text table."""
    rows = [["" if v is None else str(v) for v in r] for r in rows]
    widths = [max(len(str(c)), *(len(r[i]) for r in rows)) if rows else len(str(c))
              for i, c in enumerate(columns)]
    line = "  ".join(str(c).ljust(w) for c, w in zip(columns, widths))
    print("  " + line)
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(v.ljust(w) for v, w in zip(r, widths)))
    if not rows:
        print("  (no rows)")
