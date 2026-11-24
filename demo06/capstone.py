"""Module 6 CAPSTONE - a mini GraphRAG Q&A, built end to end and compared with vector-only RAG.

It reuses one idea from every module, on a NEW domain (medication safety):
    BUILD     corpus -> extract facts (Module 3) -> resolve names (Module 3) -> graph (Module 2)
    ANSWER    GraphRAG: entity linking + multi-hop paths (Module 4)   vs   vector-only RAG (Module 1)
    EVALUATE  context recall and precision on a multi-hop QA set (Module 5)

Run the whole capstone:   python capstone.py
Ask your own question:    python capstone.py ask "Why is Ibuprofen risky for Chen Li?"
Let a local LLM write the final answer (optional):
                          python capstone.py ask "Why is Ibuprofen risky for Chen Li?" --ollama
"""
import json
import re
import sys
from pathlib import Path

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
OLLAMA_MODEL = "qwen2.5:1.5b"

# ----------------------------------------------------------------------------- BUILD
# 1. Corpus: one short document = one chunk.
DOCS = {p.stem: p.read_text(encoding="utf-8").strip() for p in sorted((HERE / "corpus").glob("*.txt"))}

# 2. Extraction: what an LLM returned for each document (see demo03 for the live LLM version).
RAW = json.loads((HERE / "sample_extractions.json").read_text(encoding="utf-8"))
TRIPLES = [(*t, doc) for doc in DOCS for t in RAW.get(doc, [])]   # (src, src_type, rel, tgt, tgt_type, doc)

# 3. Entity resolution: "Ms. Rao" = "Asha Rao", "Chen" = "Chen Li", "warfarin" = "Warfarin".
TITLES = {"dr", "ms", "mr", "mrs"}


def tokens(name):
    return [w for w in re.findall(r"[a-z]+", name.lower()) if w not in TITLES]


def resolve(triples):
    names = {(t[0], t[1]) for t in triples} | {(t[3], t[4]) for t in triples}
    canonical = {}
    for name, etype in sorted(names, key=lambda n: (-len(n[0]), n[0])):        # longest name first
        match = [c for c, ct in canonical.values() if ct == etype and set(tokens(name)) <= set(tokens(c))]
        canonical[name] = (match[0], etype) if match else (name, etype)
    return {n: c for n, (c, _) in canonical.items()}


CANON = resolve(TRIPLES)

# 4. The graph: one edge per fact, remembering its relation and source document.
G = nx.Graph()
TYPES = {}
for src, st, rel, tgt, tt, doc in TRIPLES:
    s, t = CANON[src], CANON[tgt]
    TYPES[s], TYPES[t] = st, tt
    G.add_edge(s, t, fact=f"{s} {rel} {t}", doc=doc)


# ----------------------------------------------------------------------------- ANSWER
def link(question):
    """Entity linking: graph entities whose name words all appear in the question."""
    q = set(re.findall(r"[a-z]+", question.lower()))
    found = [n for n in G if tokens(n) and set(tokens(n)) <= q]
    return sorted(found, key=lambda n: question.lower().find(tokens(n)[0]))


def graph_rag(question):
    """2+ entities: every shortest path between them. 1 entity: its direct facts."""
    seeds = link(question)
    if len(seeds) >= 2 and nx.has_path(G, seeds[0], seeds[1]):
        edges = {tuple(sorted(e)) for p in nx.all_shortest_paths(G, seeds[0], seeds[1]) for e in zip(p, p[1:])}
    elif seeds:
        edges = {tuple(sorted(e)) for e in G.edges(seeds[0])}
    else:
        edges = set()
    return sorted(G.edges[e]["fact"] for e in edges)


VEC = TfidfVectorizer(stop_words="english").fit(DOCS.values())
MATRIX = VEC.transform(DOCS.values())


def vector_rag(question, k=2):
    """Top-k most similar documents; the context is every fact extracted from them."""
    sims = cosine_similarity(VEC.transform([question]), MATRIX)[0]
    top = [list(DOCS)[i] for i in sims.argsort()[::-1][:k]]
    facts = sorted(G.edges[e]["fact"] for e in G.edges if G.edges[e]["doc"] in top)
    return facts, top


def ollama_answer(question, facts):
    """Optional: a local LLM turns the retrieved facts into one readable answer."""
    import urllib.request
    prompt = "Answer the question using ONLY these facts. Be brief.\nFACTS:\n" + "\n".join(facts) + f"\nQUESTION: {question}"
    body = json.dumps({"model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/chat", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["message"]["content"].strip()
    except Exception as e:
        return f"(Ollama unavailable: {type(e).__name__})"


# ----------------------------------------------------------------------------- EVALUATE
def evaluate():
    qa = json.loads((HERE / "qa_set.json").read_text(encoding="utf-8"))
    print(f"\n  {'question':<52}{'hops':>4}{'Vector recall':>15}{'Graph recall':>14}")
    total = {"Vector": [0, 0, 0], "Graph": [0, 0, 0]}          # recall, precision, fully answered
    for q in qa:
        results = {"Vector": vector_rag(q["question"])[0], "Graph": graph_rag(q["question"])}
        row = f"  {q['question']:<52}{q['hops']:>4}"
        for name, got in results.items():
            hit = len(set(got) & set(q["gold"]))
            recall, precision = hit / len(q["gold"]), hit / len(got) if got else 0
            total[name][0] += recall
            total[name][1] += precision
            total[name][2] += recall == 1
            row += f"{recall:>15.0%}" if name == "Vector" else f"{recall:>14.0%}"
        print(row)
    n = len(qa)
    print()
    for name, (r, p, a) in total.items():
        print(f"  {name + ' RAG':<11} context recall {r / n:>5.0%}   context precision {p / n:>5.0%}   fully answered {a}/{n}")


def ask(question, use_llm):
    facts, docs = vector_rag(question)
    print(f"\nQ: {question}")
    print(f"\n  VECTOR-ONLY RAG  (top documents: {', '.join(docs)})")
    print("    " + "\n    ".join(facts or ["(nothing)"]))
    graph = graph_rag(question)
    print(f"\n  GRAPHRAG  (entities linked: {', '.join(link(question)) or 'none'})")
    print("    " + "\n    ".join(graph or ["(nothing)"]))
    if use_llm:
        print(f"\n  Answer written by {OLLAMA_MODEL} from the GraphRAG facts:\n    {ollama_answer(question, graph)}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "ask":
        ask(sys.argv[2], "--ollama" in sys.argv)
        sys.exit()

    print("BUILD")
    print(f"  1. Corpus:     {len(DOCS)} documents")
    print(f"  2. Extract:    {len(TRIPLES)} facts")
    merged = {raw: c for raw, c in CANON.items() if raw != c}
    print(f"  3. Resolve:    {len(CANON)} names -> {len(set(CANON.values()))} entities   "
          + ", ".join(f"'{r}'->'{c}'" for r, c in merged.items()))
    print(f"  4. Graph:      {G.number_of_nodes()} nodes, {G.number_of_edges()} relationships")

    print("\nANSWER  (one example, both systems)")
    ask("How is Dr. Mehta linked to Aspirin?", False)

    print("\nEVALUATE  (multi-hop QA set)")
    evaluate()
