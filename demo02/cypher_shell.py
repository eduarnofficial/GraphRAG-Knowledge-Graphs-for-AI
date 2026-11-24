"""Interactive Cypher prompt for the graph built by 01_property_graph.py.

Use it live in class: type a query, press Enter, see the table.
A query can span several lines; it runs when a line ends with ';'.

    python cypher_shell.py

Try these:
    MATCH (v:Vendor) RETURN v.name, v.risk;
    MATCH (p:Person)-[:DIRECTOR_OF]->(c:Company) RETURN p.name, c.name;
    MATCH (v:Vendor {name: 'Apex Logistics'})-[:OWNED_BY*1..5]->(c) RETURN c.name;
    CALL show_tables() RETURN *;
Type  exit  to quit.
"""
import kuzu

from common import OUTPUT, print_table

DB_PATH = OUTPUT / "acme_kuzu"

if not DB_PATH.exists():
    raise SystemExit("Run  python 01_property_graph.py  first - it builds the database.")

conn = kuzu.Connection(kuzu.Database(str(DB_PATH)))
print(__doc__)

buffer = []
while True:
    try:
        line = input("cypher> " if not buffer else "   ...> ")
    except EOFError:
        break
    if line.strip().lower() in {"exit", "quit"}:
        break
    buffer.append(line)
    if not line.rstrip().endswith(";"):
        continue
    query = "\n".join(buffer).rstrip().rstrip(";")
    buffer = []
    try:
        result = conn.execute(query)
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        print_table(result.get_column_names(), rows)
    except Exception as e:          # show the error and keep the prompt alive
        print(f"  ERROR: {e}")
