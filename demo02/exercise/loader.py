"""Shared plumbing for the exercise: create the database, load CSVs, run queries.

You do NOT need to edit this file. Your work goes in starter.py.
"""
import re
import shutil
import sys
from pathlib import Path

import kuzu

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import banner, print_table, read_csv  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"


def run(conn, cypher, params=None):
    result = conn.execute(cypher, params or {})
    cols, rows = result.get_column_names(), []
    while result.has_next():
        rows.append(result.get_next())
    return cols, rows


def create_db(schema_text, name):
    """Create a fresh database in exercise/output/<name> and apply your schema."""
    path = HERE / "output" / name
    path.parent.mkdir(exist_ok=True)
    # start clean: remove the database AND its .wal log file (a leftover log would replay old tables)
    for old in path.parent.glob(path.name + "*"):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    conn = kuzu.Connection(kuzu.Database(str(path)))
    for stmt in [s.strip() for s in re.sub(r"//.*", "", schema_text).split(";") if s.strip()]:
        run(conn, stmt)
    return conn


def load(conn):
    """Load the healthcare CSVs. Assumes the node/relationship names suggested in the README."""
    rd = lambda n: read_csv(n, DATA)
    for p in rd("patients"):
        run(conn, "CREATE (:Patient {id: $id, name: $name, age: $age})", {**p, "age": int(p["age"])})
    for d in rd("drugs"):
        run(conn, "CREATE (:Drug {id: $id, name: $name, drug_class: $drug_class})", d)
    for c in rd("conditions"):
        run(conn, "CREATE (:Condition {id: $id, name: $name})", c)
    for r in rd("takes"):
        run(conn, """MATCH (p:Patient {id: $p}), (d:Drug {id: $d})
                     CREATE (p)-[:TAKES {dose_mg: $dose, since: $since}]->(d)""",
            {"p": r["patient_id"], "d": r["drug_id"], "dose": float(r["dose_mg"]), "since": int(r["since"])})
    for r in rd("has_condition"):
        run(conn, "MATCH (p:Patient {id: $p}), (c:Condition {id: $c}) CREATE (p)-[:HAS_CONDITION]->(c)",
            {"p": r["patient_id"], "c": r["condition_id"]})
    for r in rd("treats"):
        run(conn, "MATCH (d:Drug {id: $d}), (c:Condition {id: $c}) CREATE (d)-[:TREATS]->(c)",
            {"d": r["drug_id"], "c": r["condition_id"]})
    for r in rd("interacts_with"):
        run(conn, """MATCH (a:Drug {id: $a}), (b:Drug {id: $b})
                     CREATE (a)-[:INTERACTS_WITH {severity: $sev, effect: $eff}]->(b)""",
            {"a": r["drug_a"], "b": r["drug_b"], "sev": r["severity"], "eff": r["effect"]})


def answer(conn, title, cypher, params=None):
    banner(title, "-")
    if not cypher.strip() or "TODO" in cypher:
        print("  (not written yet - fill in the TODO in starter.py)")
        return
    print("  " + cypher.strip().replace("\n", "\n  "))
    print()
    try:
        cols, rows = run(conn, cypher, params)
        print_table(cols, rows)
    except Exception as e:
        print(f"  ERROR: {e}")
