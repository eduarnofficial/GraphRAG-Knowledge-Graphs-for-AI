"""STEP 2 - The same data as an RDF graph: ontology, triples and SPARQL.

What this script does, in order:
  1. Loads the ontology (ontology/acme_ontology.ttl): classes, subclasses, domain/range.
  2. Turns the same CSV files into RDF TRIPLES (subject - predicate - object).
  3. Shows one vendor in Turtle, so you can see what triples look like.
  4. Runs a SPARQL tour, with the same questions as the Cypher tour in step 1.
  5. Shows the "open world": RDF accepts a triple that breaks the ontology,
     and we catch it with a validation query (in production you would use SHACL).
  6. Saves output/acme_data.ttl, which opens in any RDF tool (Protégé, GraphDB, Jena ...).

Run:   python 02_rdf_graph.py
"""
import textwrap

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace

from common import HERE, OUTPUT, banner, print_table, read_csv

ACME = Namespace("http://example.org/acme#")


# ----------------------------------------------------------------------------
# 1 + 2. Build the RDF graph: ontology triples + data triples
# ----------------------------------------------------------------------------
def build_graph():
    g = Graph()
    g.bind("acme", ACME)

    # The ontology is just more triples, so it lives in the same graph as the data.
    g.parse(HERE / "ontology" / "acme_ontology.ttl", format="turtle")
    ontology_triples = len(g)

    # Every thing gets a URI (a global id): acme:V1, acme:C4, ...
    # A triple is written as g.add((subject, predicate, object)).
    for v in read_csv("vendors"):
        s = ACME[v["id"]]
        g.add((s, RDF.type, ACME.Vendor))                      # "V1 is a Vendor"
        g.add((s, ACME.name, Literal(v["name"])))              # "V1 has name 'Apex Logistics'"
        g.add((s, ACME.risk, Literal(v["risk"])))
        g.add((s, ACME.country, Literal(v["country"])))

    for c in read_csv("companies"):
        s = ACME[c["id"]]
        g.add((s, RDF.type, ACME.Company))
        g.add((s, ACME.name, Literal(c["name"])))
        g.add((s, ACME.country, Literal(c["country"])))
        g.add((s, ACME.sanctioned, Literal(c["sanctioned"] == "true", datatype=XSD.boolean)))
        if c["sanctions_list"]:
            g.add((s, ACME.sanctionsList, Literal(c["sanctions_list"])))

    for p in read_csv("people"):
        s = ACME[p["id"]]
        g.add((s, RDF.type, ACME.Person))
        g.add((s, ACME.name, Literal(p["name"])))
        g.add((s, ACME.role, Literal(p["role"])))

    for a in read_csv("addresses"):
        s = ACME[a["id"]]
        g.add((s, RDF.type, ACME.Address))
        g.add((s, ACME.name, Literal(f"{a['line']}, {a['city']}")))

    # OWNED_BY carries a share and a year. A triple cannot hold extra values, so we:
    #   (a) add the simple triple, which makes traversal easy:  V1 ownedBy C1
    #   (b) add an Ownership node holding the details:          own_V1_C1 sharePct 100
    for r in read_csv("owned_by"):
        g.add((ACME[r["from_id"]], ACME.ownedBy, ACME[r["to_id"]]))
        stake = ACME[f"own_{r['from_id']}_{r['to_id']}"]
        g.add((stake, RDF.type, ACME.Ownership))
        g.add((stake, ACME.ownedEntity, ACME[r["from_id"]]))
        g.add((stake, ACME.owner, ACME[r["to_id"]]))
        g.add((stake, ACME.sharePct, Literal(r["share_pct"], datatype=XSD.decimal)))
        g.add((stake, ACME.since, Literal(int(r["since"]))))

    for r in read_csv("director_of"):
        g.add((ACME[r["person_id"]], ACME.directorOf, ACME[r["company_id"]]))
    for r in read_csv("approved"):
        g.add((ACME[r["person_id"]], ACME.approved, ACME[r["vendor_id"]]))
    for r in read_csv("registered_at"):
        g.add((ACME[r["org_id"]], ACME.registeredAt, ACME[r["address_id"]]))

    return g, ontology_triples


# ----------------------------------------------------------------------------
# 4. SPARQL tour - the same questions as the Cypher tour
# ----------------------------------------------------------------------------
# SPARQL matches TRIPLE PATTERNS. Variables start with '?'.
#   ?v a acme:Vendor .            -> find every ?v whose type is Vendor
#   ?v acme:ownedBy+ ?c .         -> one or more ownedBy hops (a property path)
PREFIXES = """
PREFIX acme: <http://example.org/acme#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

SPARQL = [
    ("S1  High-risk vendors   (Cypher Q2)",
     "Two triple patterns joined on ?v: it is a Vendor AND its risk is 'high'.",
     """SELECT ?vendor WHERE {
          ?v a acme:Vendor ;
             acme:risk "high" ;
             acme:name ?vendor .
        }"""),

    ("S2  Who owns each vendor, with share   (Cypher Q3)",
     "Relationship properties live on the Ownership node, so we go through it. Compare with Cypher Q3.",
     """SELECT ?vendor ?owner ?share ?since WHERE {
          ?stake a acme:Ownership ;
                 acme:ownedEntity ?v ; acme:owner ?c ;
                 acme:sharePct ?share ; acme:since ?since .
          ?v a acme:Vendor ; acme:name ?vendor .
          ?c acme:name ?owner .
        }"""),

    ("S3  Full ownership chain of Apex   (Cypher Q5)",
     "ownedBy+ is a property path: follow ownedBy one or more times.",
     """SELECT ?owner WHERE {
          ?v acme:name "Apex Logistics" ;
             acme:ownedBy+ ?c .
          ?c acme:name ?owner .
        }"""),

    ("S4  Ontology at work: list every Organization",
     "No node is typed 'Organization'. rdf:type/rdfs:subClassOf* walks up the class tree.",
     """SELECT ?org ?type WHERE {
          ?x a ?cls ; acme:name ?org .
          ?cls rdfs:subClassOf* acme:Organization .
          BIND(STRAFTER(STR(?cls), "#") AS ?type)
        } ORDER BY ?type ?org"""),

    ("S5  Director in the chain on a sanctioned board   (Cypher Q6)",
     "The same 4-hop pattern as Cypher, written as triple patterns.",
     """SELECT ?vendor ?director ?sanctioned WHERE {
          ?v a acme:Vendor ; acme:name ?vendor ;
             acme:ownedBy+ ?c .
          ?p acme:directorOf ?c ;
             acme:directorOf ?s ;
             acme:name ?director .
          ?s acme:sanctioned true ; acme:name ?sanctioned .
        }"""),

    ("S6  Shared registered address   (Cypher Q7)",
     "Two subjects point to the same address object.",
     """SELECT ?vendor ?address ?company WHERE {
          ?v a acme:Vendor ; acme:registeredAt ?a ; acme:name ?vendor .
          ?s acme:sanctioned true ; acme:registeredAt ?a ; acme:name ?company .
          ?a acme:name ?address .
        }"""),
]


def sparql_tour(g):
    for title, why, query in SPARQL:
        banner(title, "-")
        print(f"  Why: {why}\n")
        print(textwrap.indent(textwrap.dedent("        " + query.strip()), "  "))
        print()
        res = g.query(PREFIXES + query)
        print_table([str(v) for v in res.vars], [[str(x) for x in row] for row in res])


# ----------------------------------------------------------------------------
# 5. Open world + validation
# ----------------------------------------------------------------------------
# Domain check: for every triple whose predicate has an rdfs:domain,
# is the subject really of that type (or of a subclass of it)?
DOMAIN_CHECK = """
SELECT ?subject ?property ?expected WHERE {
  ?s ?p ?o .
  ?p rdfs:domain ?d .
  FILTER NOT EXISTS { ?s a/rdfs:subClassOf* ?d }
  BIND(STRAFTER(STR(?s), "#") AS ?subject)
  BIND(STRAFTER(STR(?p), "#") AS ?property)
  BIND(STRAFTER(STR(?d), "#") AS ?expected)
}"""


def open_world_demo(g):
    banner("Open world - RDF accepts a triple that breaks the ontology")
    print("  Adding:  acme:C1 acme:approved acme:V1   (a COMPANY 'approving' a vendor)")
    g.add((ACME.C1, ACME.approved, ACME.V1))
    print("  -> accepted. RDF stores any triple; the ontology describes, it does not block.")
    print("\n  Validation query: subjects whose type does not match the property's rdfs:domain\n")
    res = g.query(PREFIXES + DOMAIN_CHECK)
    print_table([str(v) for v in res.vars], [[str(x) for x in row] for row in res])
    print("\n  In production you would express such rules in SHACL and validate on every load.")
    g.remove((ACME.C1, ACME.approved, ACME.V1))


if __name__ == "__main__":
    banner("STEP 2 - RDF graph + ontology + SPARQL (rdflib)")
    g, n_onto = build_graph()
    print(f"  {n_onto} ontology triples + {len(g) - n_onto} data triples = {len(g)} triples")

    banner("What does one vendor look like as triples? (Turtle)")
    apex = Graph()
    apex.bind("acme", ACME)
    for t in g.triples((ACME.V1, None, None)):
        apex.add(t)
    print(apex.serialize(format="turtle"))

    sparql_tour(g)
    open_world_demo(g)

    OUTPUT.mkdir(exist_ok=True)
    g.serialize(OUTPUT / "acme_data.ttl", format="turtle")
    banner("Saved")
    print(f"  {OUTPUT / 'acme_data.ttl'}  (open it in Protégé, GraphDB or any RDF tool)")
