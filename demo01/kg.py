"""Step 1 - turn documents into a knowledge graph.

Documents -> sentences -> (subject, RELATION, object) triples + entity properties
-> validated against the ontology -> networkx graph.

In production the extraction step is usually an LLM prompted with the ontology
("extract entities of these types and relations of these types"). Here it is a
small rule-based extractor so the demo runs offline and is fully deterministic.
"""
import json
import re
from pathlib import Path

import networkx as nx

DATA_DIR = Path(__file__).parent / "data"


def load_documents():
    return json.loads((DATA_DIR / "documents.json").read_text(encoding="utf-8"))


def load_ontology():
    return json.loads((DATA_DIR / "ontology.json").read_text(encoding="utf-8"))


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=\.)\s+", text) if s.strip()]


class Extractor:
    """Pattern-based entity + relation extractor driven by the ontology gazetteer."""

    def __init__(self, ontology):
        self.ontology = ontology
        self.entity_types = ontology["entities"]
        names = sorted(self.entity_types, key=len, reverse=True)
        ent = "(?:" + "|".join(re.escape(n) for n in names) + ")"
        self.relation_patterns = [
            ("OWNED_BY", re.compile(rf"(?P<s>{ent}) is owned by (?P<o>{ent})\.")),
            ("DIRECTOR_OF", re.compile(rf"(?P<s>{ent}) is a director of (?P<o>{ent})\.")),
            ("APPROVED", re.compile(rf"(?P<s>{ent}) approved the onboarding of (?P<o>{ent})\.")),
            ("REGISTERED_AT", re.compile(rf"(?P<s>{ent}) is registered at (?P<o>[^.]+?)\.$")),
        ]
        self.property_patterns = [
            ("sanctions_list", re.compile(rf"(?P<s>{ent}) is listed on the (?P<v>[\w ]+?) sanctions list\.")),
            ("risk", re.compile(rf"(?P<s>{ent}) has a risk rating of (?P<v>\w+)\.")),
            ("service", re.compile(rf"(?P<s>{ent}) is a vendor providing (?P<v>[^.]+?)\.$")),
            ("role", re.compile(rf"(?P<s>{ent}) is the (?P<v>[^.]+?) at Acme Corp\.")),
        ]

    def type_of(self, name, default="Address"):
        return self.entity_types.get(name, default)

    def extract(self, source_id, text):
        facts = []
        for sentence in split_sentences(text):
            for rel, pat in self.relation_patterns:
                m = pat.search(sentence)
                if m:
                    facts.append({"kind": "rel", "s": m["s"], "rel": rel, "o": m["o"].strip(),
                                  "source": source_id, "sentence": sentence})
            for key, pat in self.property_patterns:
                m = pat.search(sentence)
                if m:
                    facts.append({"kind": "prop", "s": m["s"], "key": key, "v": m["v"].strip(),
                                  "source": source_id, "sentence": sentence})
        return facts

    def valid(self, fact):
        """Ontology check: reject triples whose subject/object types violate domain/range."""
        if fact["kind"] != "rel":
            return True
        schema = self.ontology["relations"][fact["rel"]]
        return (self.type_of(fact["s"]) in schema["domain"]
                and self.type_of(fact["o"]) in schema["range"])


def build_graph(facts, extractor):
    """Nodes carry `type`, `props`, `sources`; edges carry `rel`, `sources`, `evidence`."""
    G = nx.DiGraph()

    def ensure(name):
        if name not in G:
            G.add_node(name, type=extractor.type_of(name), props={}, sources=set(), prop_sources=set())

    for f in facts:
        if not extractor.valid(f):
            continue
        ensure(f["s"])
        G.nodes[f["s"]]["sources"].add(f["source"])
        if f["kind"] == "prop":
            G.nodes[f["s"]]["props"][f["key"]] = f["v"]
            G.nodes[f["s"]]["prop_sources"].add(f["source"])
            if f["key"] == "sanctions_list":
                G.nodes[f["s"]]["props"]["sanctioned"] = True
        else:
            ensure(f["o"])
            G.nodes[f["o"]]["sources"].add(f["source"])
            if G.has_edge(f["s"], f["o"]):
                G.edges[f["s"], f["o"]]["sources"].add(f["source"])
            else:
                G.add_edge(f["s"], f["o"], rel=f["rel"], sources={f["source"]}, evidence=f["sentence"])
    return G


def build_from_documents(documents, ontology):
    extractor = Extractor(ontology)
    facts = []
    for d in documents:
        facts.extend(extractor.extract(d["id"], d["text"]))
    return build_graph(facts, extractor), facts, extractor


# ---------------------------------------------------------------- exports

def to_json(G):
    return {
        "nodes": [{"id": n, "type": d["type"], "props": d["props"], "sources": sorted(d["sources"])}
                  for n, d in G.nodes(data=True)],
        "edges": [{"source": u, "target": v, "rel": d["rel"], "sources": sorted(d["sources"]),
                   "evidence": d["evidence"]} for u, v, d in G.edges(data=True)],
    }


def to_cypher(G):
    """Cypher you can paste into Neo4j Browser to load the same graph."""
    def q(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"

    lines = ["// Generated by demo01 - paste into Neo4j Browser", "MATCH (n) DETACH DELETE n;"]
    for n, d in G.nodes(data=True):
        props = {"name": n, **d["props"]}
        body = ", ".join(f"{k}: {q(v)}" for k, v in props.items())
        lines.append(f"CREATE (:{d['type']} {{{body}}});")
    for u, v, d in G.edges(data=True):
        lines.append(f"MATCH (a {{name: {q(u)}}}), (b {{name: {q(v)}}}) "
                     f"CREATE (a)-[:{d['rel']} {{sources: {q(','.join(sorted(d['sources'])))}}}]->(b);")
    return "\n".join(lines) + "\n"
