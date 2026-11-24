"""Web UI: vector-only RAG vs GraphRAG side by side, with the knowledge graph drawn live.

    python app.py      ->  http://127.0.0.1:5001
"""
import os

import networkx as nx
from flask import Flask, jsonify, render_template, request

from graph_rag import GraphRAG
from kg import load_documents, load_ontology
from vector_rag import VectorRAG

app = Flask(__name__)

DOCS, ONTO = load_documents(), load_ontology()
GRAG = GraphRAG(DOCS, ONTO)
VRAG = VectorRAG(DOCS, GRAG.extractor)
def layout(G):
    """Lay out each connected component in its own box (largest on the left) so nothing overlaps."""
    U = G.to_undirected()
    comps = sorted(nx.connected_components(U), key=len, reverse=True)
    boxes = [(0.07, 0.0, 0.62, 1.0)]
    rest = comps[1:]
    total = sum(len(c) for c in rest) or 1
    y = 0.0
    for c in rest:
        h = len(c) / total
        boxes.append((0.68, y, 1.0, y + h))
        y += h
    pos = {}
    for comp, (x0, y0, x1, y1) in zip(comps, boxes):
        sub = nx.kamada_kawai_layout(U.subgraph(comp)) if len(comp) > 2 else \
            {n: (i, 0) for i, n in enumerate(comp)}
        xs = [p[0] for p in sub.values()]
        ys = [p[1] for p in sub.values()]
        for n, (x, yy) in sub.items():
            nx_ = (x - min(xs)) / ((max(xs) - min(xs)) or 1)
            ny_ = (yy - min(ys)) / ((max(ys) - min(ys)) or 1) if max(ys) != min(ys) else 0.5
            pos[n] = (x0 + nx_ * (x1 - x0) * 0.9, y0 + ny_ * (y1 - y0) * 0.85 + 0.05 * (y1 - y0))
    return pos


POS = layout(GRAG.G)

SAMPLES = [
    "Which of our vendors are connected to a sanctioned entity?",
    "Who ultimately controls Apex Logistics?",
    "Which vendors did Ravi Mehta approve, and which of them are high risk?",
    "How is Cobalt IT Services connected to Kestrel Trading FZE?",
    "Is Evergreen Packaging exposed to sanctions?",
    "Tell me about Viktor Petrov",
]


@app.get("/")
def index():
    return render_template("index.html", samples=SAMPLES)


@app.get("/api/graph")
def graph():
    data = GRAG.export_json()
    for n in data["nodes"]:
        n["x"], n["y"] = POS[n["id"]]
    data["stats"] = GRAG.stats()
    data["ontology"] = {k: ONTO[k] for k in ("entity_types", "relations")}
    return jsonify(data)


@app.get("/api/documents")
def documents():
    return jsonify(DOCS)


@app.post("/api/ask")
def ask():
    q = (request.get_json(force=True).get("question") or "").strip()
    if not q:
        return jsonify({"error": "empty question"}), 400
    return jsonify({"question": q, "vector": VRAG.ask(q), "graph": GRAG.ask(q)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5001)), debug=False)
