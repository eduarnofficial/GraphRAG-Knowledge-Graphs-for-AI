"""Question answering over a graph of facts.

Used by BOTH pipelines:
  * GraphRAG     -> runs on the full knowledge graph
  * Vector RAG   -> runs on a mini-graph built only from the top-k retrieved chunks

It stands in for the LLM "generation" step: it can only use facts in its context,
and every statement it makes is backed by a path of (node)-[REL]->(node) triples
plus the source document ids (provenance / citations).
"""
import re

import networkx as nx

MAX_HOPS = 6


class Result:
    def __init__(self, intent):
        self.intent = intent
        self.lines = []
        self.nodes = set()
        self.edges = set()
        self.evidence = set()
        self.paths = []

    def use_node(self, G, n):
        self.nodes.add(n)
        self.evidence |= G.nodes[n]["prop_sources"]

    def use_path(self, G, path):
        steps = []
        for a, b in zip(path, path[1:]):
            u, v = (a, b) if G.has_edge(a, b) else (b, a)
            d = G.edges[u, v]
            self.nodes |= {u, v}
            self.edges.add((u, v, d["rel"]))
            self.evidence |= d["sources"]
            steps.append(f"({u})-[:{d['rel']}]->({v})")
        self.paths.append(path)
        return steps

    def to_dict(self):
        return {
            "intent": self.intent,
            "answer": "\n".join(self.lines),
            "nodes": sorted(self.nodes),
            "edges": [{"source": u, "target": v, "rel": r} for u, v, r in sorted(self.edges)],
            "evidence": sorted(self.evidence),
            "paths": self.paths,
        }


def link_entities(question, G):
    """Entity linking: find graph nodes mentioned in the question (full name or unique first word)."""
    ql = question.lower()
    found = []
    first_words = {}
    for n in G.nodes:
        first_words.setdefault(n.lower().split()[0], []).append(n)
    for n, d in G.nodes(data=True):
        if d["type"] == "Address":
            continue
        name = n.lower()
        if name in ql:
            found.append((ql.index(name), n))
            continue
        first = name.split()[0]
        m = re.search(rf"\b{re.escape(first)}\b", ql)
        if len(first) > 3 and m and len(first_words[first]) == 1:
            found.append((m.start(), n))
    return [n for _, n in sorted(found)]


def _cite(sources):
    return " [" + ", ".join(sorted(sources)) + "]"


def answer(question, G, ontology):
    ql = question.lower()
    ents = link_entities(question, G)
    people = [e for e in ents if G.nodes[e]["type"] == "Person"]
    orgs = [e for e in ents if G.nodes[e]["type"] != "Person"]

    if "sanction" in ql:
        r = sanctions_exposure(G, ents, ontology)
    elif re.search(r"\b(own|owns|owned|owner|owners|control|controls|parent|behind)\b", ql) and orgs:
        r = ownership(G, orgs[0])
    elif "approv" in ql and people:
        r = approvals(G, people[0])
    elif len(ents) >= 2:
        r = connection(G, ents[0], ents[1])
    elif ents:
        r = facts_about(G, ents)
    else:
        r = Result("unknown")
        r.lines.append("No known entity from the question was found in the available context.")
    return r.to_dict()


# ------------------------------------------------------------------ intents

def sanctions_exposure(G, ents, ontology):
    r = Result("sanctions_exposure")
    vendors_in_q = [e for e in ents if G.nodes[e]["type"] == "Vendor"]
    candidates = vendors_in_q or [n for n, d in G.nodes(data=True) if d["type"] == "Vendor"]
    targets = [n for n, d in G.nodes(data=True) if d["props"].get("sanctioned")]

    if not targets:
        r.lines.append("No sanctioned entity appears in the available context, "
                       "so no sanctions exposure can be established.")
        if candidates:
            r.lines.append("Vendors seen in context: " + ", ".join(candidates) + ".")
        return r
    for t in targets:
        r.use_node(G, t)
    if not candidates:
        r.lines.append(f"Sanctioned entities in context: {', '.join(targets)}. "
                       "But no vendor appears in the context, so no vendor can be linked to them.")
        r.lines.append("ANSWER: no exposed vendors found (likely a false negative).")
        return r

    # Only follow relations that indicate control / shared identity (from the ontology),
    # not e.g. "the same employee approved both vendors".
    allowed = set(ontology["exposure_relations"])
    H = G.edge_subgraph([(u, v) for u, v, d in G.edges(data=True) if d["rel"] in allowed]).to_undirected()

    exposed = []
    for v in candidates:
        best = None
        for t in targets:
            if v in H and t in H and nx.has_path(H, v, t):
                p = nx.shortest_path(H, v, t)
                if len(p) - 1 <= MAX_HOPS and (best is None or len(p) < len(best)):
                    best = p
        if best:
            exposed.append((v, best))

    if not exposed:
        r.lines.append(f"Checked {len(candidates)} vendor(s) against {', '.join(targets)}: "
                       "no ownership / director / address path found in context.")
        r.lines.append("ANSWER: no exposed vendors found.")
        return r

    r.lines.append(f"ANSWER: {len(exposed)} vendor(s) are linked to a sanctioned entity:")
    for v, p in exposed:
        r.use_node(G, v)
        steps = r.use_path(G, p)
        lst = G.nodes[p[-1]]["props"].get("sanctions_list", "?")
        r.lines.append(f"  * {v} -> {p[-1]} ({lst} list), {len(p) - 1} hop(s):")
        for s in steps:
            r.lines.append(f"      {s}")
    clean = [c for c in candidates if c not in dict(exposed)]
    if clean:
        r.lines.append("No path found for: " + ", ".join(clean) + ".")
    return r


def ownership(G, entity):
    r = Result("ownership")
    chain = [entity]
    while True:
        parents = [v for v in G.successors(chain[-1])
                   if G.edges[chain[-1], v]["rel"] == "OWNED_BY" and v not in chain]
        if not parents:
            break
        chain.append(parents[0])
    if len(chain) == 1:
        r.nodes.add(entity)
        r.lines.append(f"ANSWER: no ownership information for {entity} in the available context.")
        return r

    steps = r.use_path(G, chain)
    r.lines.append(f"ANSWER: the ultimate parent of {entity} in the available data is {chain[-1]}.")
    r.lines.append("Ownership chain:")
    r.lines += [f"   {s}" for s in steps]

    for company in chain[1:]:
        directors = [p for p in G.predecessors(company) if G.edges[p, company]["rel"] == "DIRECTOR_OF"]
        for p in directors:
            r.use_path(G, [p, company])
            r.lines.append(f"{company} is controlled by director {p}" + _cite(G.edges[p, company]["sources"]))
            for other in G.successors(p):
                if other != company and G.edges[p, other]["rel"] == "DIRECTOR_OF":
                    r.use_path(G, [p, other])
                    flag = G.nodes[other]["props"].get("sanctioned")
                    r.use_node(G, other)
                    r.lines.append(f"   ! {p} is also a director of {other}"
                                   + (f" - SANCTIONED ({G.nodes[other]['props']['sanctions_list']})" if flag else "")
                                   + _cite(G.edges[p, other]["sources"]))
    return r


def approvals(G, person):
    r = Result("approvals")
    r.use_node(G, person)
    vendors = [v for v in G.successors(person) if G.edges[person, v]["rel"] == "APPROVED"]
    if not vendors:
        r.lines.append(f"ANSWER: no approvals by {person} found in the available context.")
        return r
    high, unknown = [], []
    r.lines.append(f"ANSWER: {person} approved {len(vendors)} vendor(s):")
    for v in vendors:
        r.use_path(G, [person, v])
        r.use_node(G, v)
        risk = G.nodes[v]["props"].get("risk")
        if risk == "high":
            high.append(v)
        if risk is None:
            unknown.append(v)
        r.lines.append(f"   * {v} - risk: {risk or 'UNKNOWN (not in context)'}")
    r.lines.append(f"High-risk vendors approved by {person}: {', '.join(high) if high else 'none found'}.")
    if unknown:
        r.lines.append(f"Warning: risk rating missing for {len(unknown)} vendor(s) - answer may be incomplete.")
    return r


def connection(G, a, b):
    r = Result("connection")
    U = G.to_undirected(as_view=True)
    if not nx.has_path(U, a, b):
        r.nodes |= {a, b}
        r.lines.append(f"ANSWER: no connection between {a} and {b} found in the available context.")
        return r
    p = nx.shortest_path(U, a, b)
    steps = r.use_path(G, p)
    r.lines.append(f"ANSWER: {a} and {b} are connected in {len(p) - 1} hop(s):")
    r.lines += [f"   {s}" for s in steps]
    return r


def facts_about(G, ents):
    r = Result("facts")
    for e in ents:
        r.use_node(G, e)
        props = {k: v for k, v in G.nodes[e]["props"].items()}
        r.lines.append(f"{e} ({G.nodes[e]['type']})" + (f": {props}" if props else ""))
        for nb in list(G.successors(e)) + list(G.predecessors(e)):
            r.lines.append("   " + r.use_path(G, [e, nb])[0])
    return r
