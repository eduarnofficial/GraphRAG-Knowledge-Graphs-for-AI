"""Module 5 demo - evaluation and production concerns, one small script.

    1. ANSWER QUALITY   score vector RAG vs GraphRAG on a multi-hop QA set (RAGAS-style metrics)
    2. COST & LATENCY   time each retriever, count context tokens, estimate cost per 1,000 questions
    3. INCREMENTAL UPDATE   add one new document; re-summarise only the communities that changed
    4. ACCESS CONTROL   the same question, three user roles, an audit log

Run:  python eval_demo.py          (no API key, no internet)
"""
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent


def read(name):
    with open(HERE / "data" / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


CHUNKS = {r["id"]: r for r in read("chunks")}
FACTS = {r["id"]: r for r in read("facts")}
QA = json.loads((HERE / "data" / "qa_set.json").read_text(encoding="utf-8"))
ENTITIES = sorted({f[k] for f in FACTS.values() for k in ("source", "target")}, key=len, reverse=True)

# Example prices only - replace with your own model's price per million tokens.
PRICE_IN, PRICE_OUT, ANSWER_TOKENS = 3.00, 15.00, 150


def fact_text(fid):
    f = FACTS[fid]
    return f"{f['source']} {f['relation']} {f['target']}"


def tokens(text):
    return len(text) // 4                      # rule of thumb: ~4 characters per token


# -----------------------------------------------------------------------------
# The two systems under test. "allowed" = the sensitivity levels this user may see.
# -----------------------------------------------------------------------------
ALL_LEVELS = {"public", "internal", "restricted"}


_INDEX = {}


def vector_index(allowed):
    """Build the vector index once per set of allowed chunks (as a real vector store would)."""
    key = (frozenset(allowed), len(CHUNKS))
    if key not in _INDEX:
        ids = [c for c in CHUNKS if CHUNKS[c]["sensitivity"] in allowed]
        vec = TfidfVectorizer(stop_words="english").fit([CHUNKS[c]["text"] for c in ids])
        _INDEX[key] = (ids, vec, vec.transform([CHUNKS[c]["text"] for c in ids]))
    return _INDEX[key]


def vector_rag(question, allowed=ALL_LEVELS, k=2):
    """Top-k most similar chunks; the context is every fact inside them."""
    ids, vec, matrix = vector_index(allowed)
    sims = cosine_similarity(vec.transform([question]), matrix)[0]
    top = [ids[i] for i in sims.argsort()[::-1][:k]]
    facts = [f for f in FACTS if FACTS[f]["chunk"] in top]
    return facts, " ".join(CHUNKS[c]["text"] for c in top)


def graph_rag(question, allowed=ALL_LEVELS):
    """Entity linking + traversal. 2+ entities: shortest path between them. 1 entity: its neighbours."""
    G = nx.Graph()
    for fid, f in FACTS.items():
        if CHUNKS[f["chunk"]]["sensitivity"] in allowed:
            if f["relation"] != "APPROVED" or "approv" in question.lower():   # follow control links only
                G.add_edge(f["source"], f["target"], fid=fid)
    seeds = [e for e in ENTITIES if e.lower() in question.lower() and e in G]
    if len(seeds) >= 2:                                   # "how is X linked to Y": the path, or nothing
        if not nx.has_path(G, seeds[0], seeds[1]):
            return [], ""
        path = nx.shortest_path(G, seeds[0], seeds[1])
        facts = [G.edges[a, b]["fid"] for a, b in zip(path, path[1:])]
    elif seeds:
        facts = [G.edges[e]["fid"] for e in G.edges(seeds[0])]
    else:
        facts = []
    return facts, " ".join(fact_text(f) for f in facts)


SYSTEMS = {"Vector RAG": vector_rag, "GraphRAG": graph_rag}


# =============================================================================
# 1. ANSWER QUALITY - RAGAS-style context metrics on a multi-hop QA set
# =============================================================================
# RAGAS scores context precision, context recall, faithfulness and answer relevancy,
# normally using an LLM as the judge. Our QA set lists the GOLD facts for every
# question, so the two context metrics can be computed exactly, with no LLM:
#   context recall    = share of the gold facts that were retrieved   (did we find everything?)
#   context precision = share of the retrieved facts that are gold     (how much noise?)
def evaluate():
    print("\n1. ANSWER QUALITY  (multi-hop QA set, 5 questions, 1 to 5 hops)")
    print(f"  {'question':<52}{'hops':>5}   {'Vector RAG recall':>18}   {'GraphRAG recall':>16}")
    totals = {s: {"recall": 0, "precision": 0, "answerable": 0} for s in SYSTEMS}
    for q in QA:
        row = f"  {q['question']:<52}{q['hops']:>5}"
        for name, system in SYSTEMS.items():
            got, _ = system(q["question"])
            hit = len(set(got) & set(q["gold_facts"]))
            recall, precision = hit / len(q["gold_facts"]), (hit / len(got) if got else 0)
            totals[name]["recall"] += recall
            totals[name]["precision"] += precision
            totals[name]["answerable"] += recall == 1
            row += f"   {recall:>18.0%}" if name == "Vector RAG" else f"   {recall:>16.0%}"
        print(row)
    print()
    for name, t in totals.items():
        n = len(QA)
        print(f"  {name:<11} context recall {t['recall'] / n:>5.0%}   context precision {t['precision'] / n:>5.0%}"
              f"   fully answerable {t['answerable']}/{n}")
    return totals


# =============================================================================
# 2. COST AND LATENCY
# =============================================================================
def cost_and_latency():
    print("\n2. COST AND LATENCY  (per question, averaged over the QA set)")
    print(f"  {'system':<12}{'retrieval ms':>14}{'context tokens':>16}{'LLM cost per 1,000 questions':>32}")
    for name, system in SYSTEMS.items():
        start = time.perf_counter()
        for _ in range(20):
            contexts = [system(q["question"])[1] for q in QA]
        ms = (time.perf_counter() - start) * 1000 / (20 * len(QA))
        ctx = sum(tokens(c) for c in contexts) / len(QA)
        cost = 1000 * ((ctx + 100) * PRICE_IN + ANSWER_TOKENS * PRICE_OUT) / 1_000_000   # +100 tokens of prompt
        print(f"  {name:<12}{ms:>14.1f}{ctx:>16.0f}{'$' + format(cost, '.2f'):>32}")
    print(f"  Index cost: Vector RAG = embeddings only. GraphRAG = 1 LLM call per chunk ({len(CHUNKS)}) "
          f"+ 1 per community summary. Prices are examples (${PRICE_IN}/${PRICE_OUT} per million tokens).")


# =============================================================================
# 3. INCREMENTAL GRAPH UPDATE
# =============================================================================
def communities():
    G = nx.Graph()
    for f in FACTS.values():
        G.add_edge(f["source"], f["target"])
    return {frozenset(c) for c in nx.community.louvain_communities(G, seed=7, resolution=0.5)}


def incremental_update():
    print("\n3. INCREMENTAL UPDATE  (a new document arrives)")
    q = "How is Evergreen Packaging linked to OFAC?"
    before_comms = communities()
    before, _ = graph_rag(q)
    new = read("new_document")[0]
    print(f"  New document {new['chunk']}: \"{new['text']}\"")
    CHUNKS[new["chunk"]] = {"id": new["chunk"], "sensitivity": new["sensitivity"], "text": new["text"]}
    FACTS[new["id"]] = {k: new[k] for k in ("id", "source", "relation", "target", "chunk")}
    print(f"  MERGE 1 new fact: {fact_text(new['id'])}   (no full re-index)")
    after_comms = communities()
    kept, changed = before_comms & after_comms, after_comms - before_comms
    print(f"  Communities: {len(kept)} unchanged (keep their summaries), {len(changed)} changed (re-summarise only these)")
    after, _ = graph_rag(q)
    print(f"  Q: {q}")
    print(f"     before: {' -> '.join(fact_text(f) for f in before) or 'no link found'}")
    print(f"     after : {len(after)} hops: " + " | ".join(fact_text(f) for f in after))
    for fid in [new["id"]]:                                      # undo, so parts 1, 2, 4 stay comparable
        FACTS.pop(fid)
    CHUNKS.pop(new["chunk"])


# =============================================================================
# 4. ACCESS CONTROL AND GOVERNANCE
# =============================================================================
ROLES = {"external_auditor": {"public"},
         "analyst": {"public", "internal"},
         "compliance_officer": {"public", "internal", "restricted"}}


def access_control():
    print("\n4. ACCESS CONTROL  (same question, three roles; every fact is labelled with its source's sensitivity)")
    q = next(x for x in QA if x["id"] == "Q3")
    log = HERE / "output" / "audit_log.csv"
    log.parent.mkdir(exist_ok=True)
    with open(log, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "role", "question", "facts_used", "sources"])
        for role, allowed in ROLES.items():
            got, _ = graph_rag(q["question"], allowed)
            sources = sorted({FACTS[g]["chunk"] for g in got})
            answer = " | ".join(fact_text(g) for g in got) if set(q["gold_facts"]) <= set(got) else "no link visible to this role"
            print(f"  {role:<19} sees {', '.join(sorted(allowed)):<30} -> {answer}")
            writer.writerow([datetime.now().isoformat(timespec="seconds"), role, q["question"], " ".join(got), " ".join(sources)])
    print(f"  Audit log written: {log}  (who asked what, and which sources the answer used)")


if __name__ == "__main__":
    print(f"{len(CHUNKS)} chunks, {len(FACTS)} facts, {len(QA)} test questions")
    evaluate()
    cost_and_latency()
    incremental_update()
    access_control()
