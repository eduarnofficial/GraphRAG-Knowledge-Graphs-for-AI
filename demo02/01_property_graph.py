"""STEP 1 - The property graph model + Cypher, on a local graph database.

What this script does, in order:
  1. Creates an embedded graph database (Kùzu) in ./output/acme_kuzu
     Kùzu runs inside Python, like SQLite, so you need no server.
     It speaks Cypher, the same query language as Neo4j.
  2. Creates the SCHEMA from schema.cypher (node labels + relationship types).
  3. Loads the CSV files in ./data as nodes and relationships.
  4. Shows that the schema PROTECTS the data: an invalid relationship is rejected.
  5. Runs a guided tour of Cypher queries, from a simple MATCH to multi-hop paths.
  6. Writes output/neo4j_load.cypher, so the same graph can be pasted into Neo4j.

Run:   python 01_property_graph.py
Then:  python cypher_shell.py       (type your own Cypher queries)
"""
import re
import textwrap
import shutil

import kuzu

from common import OUTPUT, banner, print_table, read_csv, HERE

DB_PATH = OUTPUT / "acme_kuzu"


# ----------------------------------------------------------------------------
# Helper: run one Cypher statement and return (column names, rows)
# ----------------------------------------------------------------------------
def run(conn, cypher, params=None):
    result = conn.execute(cypher, params or {})
    columns = result.get_column_names()
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return columns, rows


# ----------------------------------------------------------------------------
# 1 + 2. Create a fresh database and apply the schema
# ----------------------------------------------------------------------------
def create_database():
    OUTPUT.mkdir(exist_ok=True)
    # start clean: remove the database AND its .wal log file (a leftover log would replay old tables)
    for old in DB_PATH.parent.glob(DB_PATH.name + "*"):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    db = kuzu.Database(str(DB_PATH))
    conn = kuzu.Connection(db)

    # schema.cypher holds several statements separated by ';'.
    # We strip the // comments and run them one by one.
    text = (HERE / "schema.cypher").read_text(encoding="utf-8")
    text = re.sub(r"//.*", "", text)
    for statement in [s.strip() for s in text.split(";") if s.strip()]:
        run(conn, statement)
    return db, conn


# ----------------------------------------------------------------------------
# 3. Load CSV rows as nodes and relationships
# ----------------------------------------------------------------------------
# Each node is created with a parameterised CREATE statement.
# Parameters ($id, $name, ...) keep values safely separate from the query text,
# the same good practice as SQL parameters.
def load_data(conn):
    for v in read_csv("vendors"):
        run(conn, "CREATE (:Vendor {id: $id, name: $name, service: $service, risk: $risk, country: $country})", v)

    for c in read_csv("companies"):
        c["sanctioned"] = c["sanctioned"] == "true"          # CSV text -> real boolean
        run(conn, """CREATE (:Company {id: $id, name: $name, kind: $kind, country: $country,
                                       sanctioned: $sanctioned, sanctions_list: $sanctions_list})""", c)

    for p in read_csv("people"):
        run(conn, "CREATE (:Person {id: $id, name: $name, role: $role})", p)

    for a in read_csv("addresses"):
        a["name"] = f"{a['line']}, {a['city']}"              # display name, e.g. "14 Harbour Road, Limassol"
        run(conn, "CREATE (:Address {id: $id, name: $name, line: $line, city: $city, country: $country})", a)

    # Relationships: first MATCH the two end nodes, then CREATE the arrow between them.
    for r in read_csv("owned_by"):
        run(conn, f"""MATCH (a:{r['from_label']} {{id: $from_id}}), (b:Company {{id: $to_id}})
                      CREATE (a)-[:OWNED_BY {{share_pct: $share, since: $since}}]->(b)""",
            {"from_id": r["from_id"], "to_id": r["to_id"],
             "share": float(r["share_pct"]), "since": int(r["since"])})

    for r in read_csv("director_of"):
        run(conn, """MATCH (p:Person {id: $p}), (c:Company {id: $c})
                     CREATE (p)-[:DIRECTOR_OF {since: $since}]->(c)""",
            {"p": r["person_id"], "c": r["company_id"], "since": int(r["since"])})

    for r in read_csv("approved"):
        run(conn, """MATCH (p:Person {id: $p}), (v:Vendor {id: $v})
                     CREATE (p)-[:APPROVED {approved_on: date($d), contract_value: $value}]->(v)""",
            {"p": r["person_id"], "v": r["vendor_id"], "d": r["approved_on"], "value": float(r["contract_value"])})

    for r in read_csv("registered_at"):
        run(conn, f"""MATCH (o:{r['org_label']} {{id: $o}}), (a:Address {{id: $a}})
                      CREATE (o)-[:REGISTERED_AT]->(a)""",
            {"o": r["org_id"], "a": r["address_id"]})


def show_counts(conn):
    banner("Graph loaded - what is inside?")
    rows = []
    for label in ["Vendor", "Company", "Person", "Address"]:
        rows.append(["node", label, run(conn, f"MATCH (n:{label}) RETURN count(n)")[1][0][0]])
    for rel in ["OWNED_BY", "DIRECTOR_OF", "APPROVED", "REGISTERED_AT"]:
        rows.append(["relationship", rel, run(conn, f"MATCH ()-[r:{rel}]->() RETURN count(r)")[1][0][0]])
    print_table(["kind", "label / type", "count"], rows)


# ----------------------------------------------------------------------------
# 4. Schema enforcement demo
# ----------------------------------------------------------------------------
def schema_guard_demo(conn):
    banner("Schema check - try to create an INVALID relationship")
    bad = "MATCH (c:Company {id: 'C1'}), (v:Vendor {id: 'V1'}) CREATE (c)-[:APPROVED]->(v)"
    print("  A COMPANY approving a vendor breaks the rule APPROVED: FROM Person TO Vendor")
    print(f"  Cypher: {bad}")
    try:
        run(conn, bad)
        print("  -> accepted (this should not happen)")
    except RuntimeError as e:
        print(f"  -> REJECTED by the database: {e}")
    print("  This is why we design the schema / ontology first: bad facts never get in.")


# ----------------------------------------------------------------------------
# 5. A guided tour of Cypher - each query is explained before it runs
# ----------------------------------------------------------------------------
# Cypher reads like ASCII art:
#   (v:Vendor)                 a node with label Vendor, bound to the name v
#   -[o:OWNED_BY]->            a relationship of type OWNED_BY, pointing right
#   -[:OWNED_BY*1..5]->        1 to 5 OWNED_BY hops in a row (variable length)
QUERIES = [
    ("Q1  MATCH + RETURN - list every vendor",
     "The simplest pattern: find all nodes with the label Vendor.",
     """MATCH (v:Vendor)
        RETURN v.name AS vendor, v.risk AS risk, v.country AS country
        ORDER BY vendor"""),

    ("Q2  WHERE - only the high-risk vendors",
     "Filter on a node property, just like SQL WHERE.",
     """MATCH (v:Vendor)
        WHERE v.risk = 'high'
        RETURN v.name AS vendor, v.service AS service"""),

    ("Q3  One hop + relationship properties - who owns each vendor?",
     "The arrow has its own properties: share_pct and since. This is hard to do in plain RDF (see step 2).",
     """MATCH (v:Vendor)-[o:OWNED_BY]->(c:Company)
        RETURN v.name AS vendor, c.name AS owner, o.share_pct AS share_pct, o.since AS since"""),

    ("Q4  Aggregation - approvals per employee",
     "count() and sum() group automatically by the non-aggregated columns (p.name).",
     """MATCH (p:Person)-[a:APPROVED]->(v:Vendor)
        RETURN p.name AS approver, count(v) AS vendors, sum(a.contract_value) AS total_value
        ORDER BY total_value DESC"""),

    ("Q5  Variable-length path - the full ownership chain of Apex Logistics",
     "*1..5 means: follow OWNED_BY one to five times. No JOINs to write, however deep the chain.",
     """MATCH (v:Vendor {name: 'Apex Logistics'})-[e:OWNED_BY*1..5]->(owner:Company)
        RETURN owner.name AS owner, length(e) AS hops
        ORDER BY hops"""),

    ("Q6  Multi-hop pattern - does a director in Apex's chain also sit on a sanctioned board?",
     "One pattern, four hops: vendor -> owners -> director -> another company that is sanctioned.",
     """MATCH (v:Vendor)-[:OWNED_BY*1..5]->(c:Company)<-[:DIRECTOR_OF]-(p:Person)-[:DIRECTOR_OF]->(s:Company)
        WHERE s.sanctioned = true
        RETURN v.name AS vendor, c.name AS owner_in_chain, p.name AS director, s.name AS sanctioned_company"""),

    ("Q7  Shared address - vendors registered where a sanctioned company is registered",
     "A classic fraud signal. Two arrows point INTO the same Address node.",
     """MATCH (v:Vendor)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(s:Company)
        WHERE s.sanctioned = true
        RETURN v.name AS vendor, a.name AS shared_address, s.name AS sanctioned_company"""),

    ("Q8  Shortest path - how is each vendor connected to a sanctioned company?",
     "Kùzu syntax: [* SHORTEST 1..6]. In Neo4j: shortestPath((v)-[*..6]-(s)). See neo4j_queries.cypher.",
     """MATCH (v:Vendor)-[e:OWNED_BY|DIRECTOR_OF|REGISTERED_AT* SHORTEST 1..6]-(s:Company)
        WHERE s.sanctioned = true
        RETURN v.name AS vendor, length(e) AS hops, properties(nodes(e), 'name') AS via"""),

    ("Q9  OPTIONAL MATCH - data quality: vendors with no known owner",
     "OPTIONAL MATCH keeps the vendor even when no owner exists, like a SQL LEFT JOIN.",
     """MATCH (v:Vendor)
        OPTIONAL MATCH (v)-[:OWNED_BY]->(c:Company)
        WITH v, c
        WHERE c IS NULL
        RETURN v.name AS vendor_without_owner_record"""),

    ("Q10 MERGE - add a new fact safely (create only if it does not exist)",
     "MERGE = find it, or create it. Running it twice does not create a duplicate.",
     """MERGE (p:Person {id: 'P6'})
        ON CREATE SET p.name = 'Grace Kim', p.role = 'Procurement analyst'
        RETURN p.id AS id, p.name AS name, p.role AS role"""),
]


def query_tour(conn):
    for title, why, cypher in QUERIES:
        banner(title, "-")
        print(f"  Why: {why}\n")
        print(textwrap.indent(textwrap.dedent("        " + cypher.strip()), "  "))
        print()
        cols, rows = run(conn, cypher)
        print_table(cols, rows)


# ----------------------------------------------------------------------------
# 6. Export the same graph as plain Cypher for Neo4j Desktop / Aura / Browser
# ----------------------------------------------------------------------------
def export_neo4j(conn):
    def lit(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if v is None or v == "":
            return "null"
        return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"

    out = ["// Generated by demo02/01_property_graph.py - paste into Neo4j Browser and run.",
           "MATCH (n) DETACH DELETE n;"]
    for label in ["Vendor", "Company", "Person", "Address"]:
        out.append(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE;")
        cols, rows = run(conn, f"MATCH (n:{label}) RETURN n")
        for (node,) in rows:
            props = {k: v for k, v in node.items() if not k.startswith("_") and v is not None}
            out.append(f"CREATE (:{label} {{" + ", ".join(f"{k}: {lit(v)}" for k, v in props.items()) + "});")
    for rel in ["OWNED_BY", "DIRECTOR_OF", "APPROVED", "REGISTERED_AT"]:
        cols, rows = run(conn, f"MATCH (a)-[r:{rel}]->(b) RETURN a.id, b.id, r")
        for a, b, r in rows:
            props = {k: (str(v) if k == "approved_on" else v) for k, v in r.items()
                     if not k.startswith("_") and v is not None}
            body = ", ".join(f"{k}: {('date(' + lit(v) + ')') if k == 'approved_on' else lit(v)}" for k, v in props.items())
            out.append(f"MATCH (a {{id: {lit(a)}}}), (b {{id: {lit(b)}}}) CREATE (a)-[:{rel} {{{body}}}]->(b);")
    path = OUTPUT / "neo4j_load.cypher"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    banner("Exported for Neo4j")
    print(f"  {path}")
    print("  Paste it into Neo4j Browser, then try the queries in neo4j_queries.cypher.")


if __name__ == "__main__":
    banner("STEP 1 - Property graph + Cypher (Kùzu embedded graph database)")
    db, conn = create_database()
    print(f"  Database created at {DB_PATH}, schema applied from schema.cypher")
    load_data(conn)
    show_counts(conn)
    schema_guard_demo(conn)
    query_tour(conn)
    export_neo4j(conn)
