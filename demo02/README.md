# Demo 02: Graph Data Modelling

This demo is for **Module 2 (0:40–1:30, 50 minutes)**. It covers the property graph vs RDF models, schema and ontology design, and an introduction to Cypher queries. The hands-on part has learners model a small domain.

It uses the same Acme procurement data as `demo01`, but this time the graph is modelled properly and stored in a real graph database.

| Tool | What it is | Why we use it |
|------|-----------|---------------|
| **Kùzu** | An embedded graph database that runs inside Python, like SQLite | It uses Cypher (Neo4j's query language) and needs no server, Docker or login |
| **rdflib** | An RDF library for Python | It stores triples, parses Turtle files and runs SPARQL queries |
| **Neo4j** (optional) | The most widely used graph database | `neo4j_queries.cypher` plus the generated load script let you run the same tour in Neo4j Desktop or Aura Free |

## Setup (once)

```powershell
cd demo02
pip install -r requirements.txt
```

## Run the demo, step by step

| Step | Command | What learners see | Time |
|------|---------|-------------------|------|
| 0 | Open `schema.cypher` | The schema: node tables, relationship tables, and the FROM/TO rules | 2 min |
| 1 | `python 01_property_graph.py` | The graph is built and loaded, and an invalid relationship is **rejected**. Then 10 Cypher queries run, from a simple `MATCH` to a shortest path. | 8 min |
| 1b | `python cypher_shell.py` | A prompt where you type your own Cypher queries live, each ending with `;` | (live) |
| 2 | Open `ontology/acme_ontology.ttl`, then `python 02_rdf_graph.py` | The same data as RDF triples: a class hierarchy, SPARQL queries, an ownership stake modelled as its own node, and an open-world validation check | 5 min |
| 3 | `python 03_compare_models.py` | The same 3 questions in Cypher and SPARQL, with a check that both give the same answer | 3 min |
| 4 | `exercise/README.md` and `python exercise/starter.py` | Hands-on: model a healthcare domain | 20 min |

## What each Cypher query teaches (`01_property_graph.py`)

| Query | Concept | Question |
|-------|---------|----------|
| Q1 | `MATCH` / `RETURN` / `ORDER BY` | List every vendor |
| Q2 | `WHERE` | Which vendors are high risk? |
| Q3 | Relationship properties | Who owns each vendor, and with what share? |
| Q4 | Aggregation: `count`, `sum` | How many approvals has each employee made, and for what total value? |
| Q5 | Variable-length paths `*1..5` | What is Apex Logistics' full ownership chain? |
| Q6 | Multi-hop pattern | Is a director in that chain on a sanctioned company's board? |
| Q7 | Two arrows pointing into one node | Does a vendor share an address with a sanctioned company? |
| Q8 | Shortest path | How is each vendor connected to a sanctioned company? |
| Q9 | `OPTIONAL MATCH` (works like a left join) | Which vendors have no owner on record? |
| Q10 | `MERGE` (creates only if missing, so it can run twice safely) | Add a new person without creating duplicates |

## Property graph vs RDF in one table

| | Property graph (Kùzu, Neo4j) | RDF (rdflib, GraphDB, Neptune) |
|---|---|---|
| Unit of data | Nodes and relationships, both with properties | Triples: subject, predicate, object |
| Identity | Local ids | Global URIs, for example `http://example.org/acme#V1` |
| Properties on a link | Built in: `-[:OWNED_BY {share_pct: 75}]->` | Needs an extra node (`acme:Ownership`) or RDF-star |
| Schema | Optional (Neo4j) or required (Kùzu) | An ontology (RDFS/OWL) describes the data. SHACL validates it. |
| Reasoning | None built in | Class hierarchies and inference, for example `subClassOf*` |
| Query language | Cypher / GQL (ISO standard since 2024) | SPARQL (W3C standard) |
| Best for | Application data, traversals, GraphRAG retrieval | Sharing and linking data across organisations, standard vocabularies, reasoning |

## Files

```
demo02/
├── README.md                 this file
├── requirements.txt          kuzu, rdflib
├── common.py                 CSV reader and table printer
├── data/*.csv                Acme vendors, companies, people, addresses and their relationships
├── schema.cypher             property graph schema (commented)
├── 01_property_graph.py      step 1: build, validate, 10-query Cypher tour, Neo4j export
├── cypher_shell.py           interactive Cypher prompt
├── neo4j_queries.cypher      the same tour in Neo4j syntax
├── ontology/acme_ontology.ttl   RDF ontology (classes, subclasses, domain and range)
├── 02_rdf_graph.py           step 2: RDF triples, SPARQL tour, open-world validation
├── 03_compare_models.py      step 3: Cypher vs SPARQL side by side
├── exercise/                 hands-on healthcare modelling (README, starter, solution)
├── Module2_Graph_Data_Modelling.pptx   slide deck for this module
└── output/                   generated: Kùzu database, acme_data.ttl, neo4j_load.cypher
```

## Using Neo4j instead (optional)

1. Run `python 01_property_graph.py`. It writes `output/neo4j_load.cypher`.
2. Open Neo4j Desktop or Aura Free, then Neo4j Browser.
3. Enable the multi-statement editor in Browser settings, then paste and run `output/neo4j_load.cypher`.
4. Run the queries in `neo4j_queries.cypher`. The few lines where Neo4j syntax differs from Kùzu are marked `NEO4J:`.
