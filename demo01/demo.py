"""Why RAG needs graphs - end-to-end terminal demo.

    python demo.py              # scripted walkthrough (4 questions, side by side)
    python demo.py -i           # then ask your own questions
    python demo.py -q "Who ultimately controls Apex Logistics?"
"""
import argparse
import json
import sys
from pathlib import Path

from graph_rag import GraphRAG
from kg import load_documents, load_ontology
from vector_rag import VectorRAG

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(__file__).parent / "output"

SCRIPT = [
    ("Multi-hop (compliance / fraud)",
     "Which of our vendors are connected to a sanctioned entity?"),
    ("Ownership chain (enterprise search / KYC)",
     "Who ultimately controls Apex Logistics?"),
    ("Aggregation across documents",
     "Which vendors did Ravi Mehta approve, and which of them are high risk?"),
    ("Explicit relationship",
     "How is Cobalt IT Services connected to Kestrel Trading FZE?"),
]


def banner(text, ch="="):
    print("\n" + ch * 100 + f"\n{text}\n" + ch * 100)


def show(question, vrag, grag):
    v, g = vrag.ask(question), grag.ask(question)
    print(f"\nQ: {question}")
    print("\n--- VECTOR-ONLY RAG " + "-" * 79)
    print(f"Retrieved top-{vrag.top_k} chunks (cosine similarity):")
    for c in v["chunks"]:
        print(f"   [{c['chunk_id']}] score={c['score']:.3f}  {c['text']}")
    print("Answer from that context:")
    print("   " + v["answer"].replace("\n", "\n   "))
    print("\n--- GRAPHRAG " + "-" * 86)
    print(f"Linked entities -> traversed {len(g['edges'])} relation(s); context sent to the LLM:")
    for t in g["context"]:
        print(f"   {t}")
    print("Answer:")
    print("   " + g["answer"].replace("\n", "\n   "))
    print(f"   Citations: {', '.join(g['evidence']) or '-'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--interactive", action="store_true")
    ap.add_argument("-q", "--question")
    args = ap.parse_args()

    docs, onto = load_documents(), load_ontology()

    banner("1) INGEST: documents -> chunks (vector index) and documents -> triples (knowledge graph)")
    grag = GraphRAG(docs, onto)
    vrag = VectorRAG(docs, grag.extractor)
    print(f"{len(docs)} documents -> {len(vrag.chunks)} chunks in the vector index")
    s = grag.stats()
    print(f"{s['facts_extracted']} facts extracted -> knowledge graph with {s['nodes']} nodes, {s['edges']} edges")
    print(f"   node types (ontology classes): {s['node_types']}")
    print(f"   relation types:                {s['relation_types']}")
    print("\nSample triples (node)-[EDGE]->(node) with properties and provenance:")
    for u, w, d in list(grag.G.edges(data=True))[:6]:
        print(f"   ({u})-[:{d['rel']}]->({w})   source={sorted(d['sources'])}")
    print(f"   (Kestrel Trading FZE) properties = {grag.G.nodes['Kestrel Trading FZE']['props']}")

    OUT.mkdir(exist_ok=True)
    (OUT / "kg.json").write_text(json.dumps(grag.export_json(), indent=2), encoding="utf-8")
    (OUT / "kg.cypher").write_text(grag.export_cypher(), encoding="utf-8")
    print(f"\nExported graph to {OUT / 'kg.json'} and {OUT / 'kg.cypher'} (load into Neo4j)")

    if args.question:
        show(args.question, vrag, grag)
        return

    for i, (label, q) in enumerate(SCRIPT, 2):
        banner(f"{i}) {label}")
        show(q, vrag, grag)

    if args.interactive:
        banner("Ask your own question (empty line to quit)")
        while True:
            try:
                q = input("\n> ").strip()
            except EOFError:
                break
            if not q:
                break
            show(q, vrag, grag)


if __name__ == "__main__":
    main()
