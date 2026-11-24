# Demo 01: Why RAG Needs Graphs

This is an end-to-end local demo that runs **vector-only RAG** and **GraphRAG** over the same 15 documents and compares their answers side by side.
It needs no API keys, no GPU and no database, and it runs offline.

## Run it

```powershell
cd demo01
pip install -r requirements.txt
python demo.py            # terminal walkthrough: ingest, then 4 scripted questions
python demo.py -i         # same, then ask your own questions
python app.py             # web UI at http://127.0.0.1:5001
```

## Scenario

Acme Corp is a fictional company. The demo answers procurement compliance and fraud questions over fragmented enterprise data: vendor master records, a corporate registry, a sanctions bulletin, a news article, approval logs, HR records and policies.
**No single document contains the answer.** The facts that connect a vendor to a sanctioned company sit in four different documents.

## What each question teaches

| # | Question | Vector-only RAG | GraphRAG | Lesson |
|---|----------|-----------------|----------|--------|
| 1 | Which vendors are connected to a sanctioned entity? | Retrieves the *policy* text, which shares the most words with the question. Says it **found nothing** (a false negative). | Finds Apex (4 hops: owner, then parent, then shared director, then sanctioned company) and Cobalt (2 hops through a shared address) | Similarity is not relevance. Multi-hop facts are scattered across documents. |
| 2 | Who ultimately controls Apex Logistics? | Stops at Northwind Holdings, the first hop | Follows the full chain: Apex, then Northwind, then Silverline, plus Silverline's directors. It also flags that Viktor Petrov sits on a sanctioned company's board. | Following a chain needs graph traversal. Top-k retrieval cannot do it. |
| 3 | Which vendors did Ravi approve, and which are high risk? | Gets 2 of the 3 approvals. One vendor's risk rating is missing. | All 3 approvals, each with its risk rating | Questions that collect facts from many places break under the top-k limit. |
| 4 | How is Cobalt connected to Kestrel? | Retrieves both companies' records but misses the shared-address sentence | Explicit 2-hop path with citations | Relationships need to be stored as data, not left implicit in text |

## Pipeline

```
                 +--> chunk -> embed (TF-IDF) -> top-k similar chunks ----------+
documents -------+                                                               +--> same reasoner --> answer
                 +--> extract triples (ontology) -> knowledge graph              |
                         question -> entity linking -> multi-hop traversal ------+   (+ citations)
```

* The comparison is fair: both pipelines use the same reasoner, in `reasoner.py`. The vector pipeline loses only because its context is missing facts.
* Real embeddings (sentence-transformers, OpenAI and others) improve how well wording is matched. They do not fix this problem, because the connecting facts are spread across separate chunks.

## Files

| File | Purpose |
|------|---------|
| `data/documents.json` | The 15 source documents |
| `data/ontology.json` | Schema: node types, relation domain and range, properties, gazetteer |
| `kg.py` | Extraction of documents into triples, ontology validation, the networkx graph, and JSON and Cypher export |
| `vector_rag.py` | Vector-only RAG baseline: chunking, TF-IDF, cosine top-k |
| `graph_rag.py` | GraphRAG: entity linking and traversal, with the subgraph used as context |
| `reasoner.py` | Answers questions with paths and source citations (stands in for the LLM) |
| `demo.py` | Terminal walkthrough |
| `app.py` + `templates/index.html` | Web UI: side-by-side answers and a live graph with the retrieved subgraph highlighted |
| `output/kg.json`, `output/kg.cypher` | Written by `demo.py`. Paste `kg.cypher` into Neo4j Browser to explore the graph with Cypher. |

## Knowledge graph basics, mapped to the code

* **Node**: an entity such as `(Apex Logistics:Vendor)`.
* **Edge**: a typed, directed relation such as `-[:OWNED_BY]->`.
* **Properties**: key/value pairs on nodes, such as `risk: high` or `sanctioned: true`. Each node and edge also records its `sources` (provenance).
* **Ontology**: the schema in `data/ontology.json`. It sets which node types each relation may connect. For example, `DIRECTOR_OF` must go from a Person to a Company. The extractor rejects any triple that breaks the schema.

## Try in Neo4j (optional)

Open Neo4j Browser and paste in `output/kg.cypher`, then run:

```cypher
MATCH p = (v:Vendor)-[:OWNED_BY|DIRECTOR_OF|REGISTERED_AT*1..6]-(s {sanctioned: true})
RETURN p
```

## Ideas for extending it

* Replace the rule-based extractor in `kg.py` with an LLM that is prompted with the ontology.
* Replace `reasoner.answer` with an LLM call. Pass it `result["context"]` (the triples) and ask it to cite sources.
* Add documents. If a sentence follows one of the patterns in `kg.py`, the graph updates automatically.
