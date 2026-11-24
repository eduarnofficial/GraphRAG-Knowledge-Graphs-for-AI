"""STEP 3 - Property graph vs RDF, side by side.

Asks the same three questions of both models, prints the two queries next to
each other, and checks that the answers match. Use it for the comparison discussion.

Run:   python 03_compare_models.py      (step 1 must have been run once)
"""
import importlib

import kuzu

from common import OUTPUT, banner

step1 = importlib.import_module("01_property_graph")   # file names start with a digit,
step2 = importlib.import_module("02_rdf_graph")        # so we import them this way

QUESTIONS = [
    ("Who owns Apex Logistics, and what share do they hold?",
     """MATCH (v:Vendor {name:'Apex Logistics'})-[o:OWNED_BY]->(c:Company)
RETURN c.name, o.share_pct""",
     """SELECT ?owner ?share WHERE {
  ?stake acme:ownedEntity ?v ; acme:owner ?c ; acme:sharePct ?share .
  ?v acme:name "Apex Logistics" .  ?c acme:name ?owner . }"""),

    ("Every company above Apex Logistics in its ownership chain",
     """MATCH (v:Vendor {name:'Apex Logistics'})-[:OWNED_BY*1..5]->(c:Company)
RETURN c.name""",
     """SELECT ?owner WHERE {
  ?v acme:name "Apex Logistics" ; acme:ownedBy+ ?c .
  ?c acme:name ?owner . }"""),

    ("Which vendors share an address with a sanctioned company?",
     """MATCH (v:Vendor)-[:REGISTERED_AT]->(a)<-[:REGISTERED_AT]-(s:Company)
WHERE s.sanctioned = true RETURN v.name""",
     """SELECT ?vendor WHERE {
  ?v a acme:Vendor ; acme:registeredAt ?a ; acme:name ?vendor .
  ?s acme:sanctioned true ; acme:registeredAt ?a . }"""),
]


def normalise(rows):
    """Turn both result types into comparable sorted tuples of text (100.0 == '100')."""
    def norm(x):
        x = str(x)
        try:
            return str(float(x))
        except ValueError:
            return x
    return sorted(tuple(norm(x) for x in r) for r in rows)


if __name__ == "__main__":
    if not (OUTPUT / "acme_kuzu").exists():
        raise SystemExit("Run  python 01_property_graph.py  first.")
    conn = kuzu.Connection(kuzu.Database(str(OUTPUT / "acme_kuzu")))
    g, _ = step2.build_graph()

    for question, cypher, sparql in QUESTIONS:
        banner(question)
        _, pg_rows = step1.run(conn, cypher)
        rdf_rows = [list(r) for r in g.query(step2.PREFIXES + sparql)]
        print("  PROPERTY GRAPH (Cypher):")
        print("    " + cypher.replace("\n", "\n    "))
        print("\n  RDF (SPARQL):")
        print("    " + sparql.replace("\n", "\n    "))
        print(f"\n  Cypher answer: {pg_rows}")
        print(f"  SPARQL answer: {[[str(x) for x in r] for r in rdf_rows]}")
        same = normalise(pg_rows) == normalise(rdf_rows)
        print(f"  Same answer from both models: {'YES' if same else 'NO'}")

    banner("Take-away")
    print("""  * Same facts, same answers - the model changes how you WRITE things, not what you can know.
  * Property graph: properties on relationships are native (o.share_pct). Queries are short.
  * RDF: global ids (URIs), shared vocabularies, class hierarchies and reasoning, standards (W3C).
    Relationship details need an extra node (acme:Ownership) or RDF-star.""")
