# Demo 05 (new data): what happens when you add new information

This is a copy of `demo05` with **3 new chunks, 4 new facts and 3 new test questions** added by hand.
Run both and compare to show how new data flows through the evaluation.

```powershell
cd C:\AI-ML\GraphRAG-Course
python demo05\eval_demo.py
python demo05_new_data\eval_demo.py
```

## What was added

**`data/chunks.csv`** (new source text)
| id | sensitivity | text |
|----|-------------|------|
| C9 | public | Delta Facility Management subcontracts its night cleaning to Zenith Cleaning Co. |
| C10 | restricted | Bank alert: Zenith Cleaning Co. pays its workers through Harbor Pay Ltd, a payment agent under review. |
| C11 | internal | Omar Haddad controls Harbor Pay Ltd and is also a shareholder of Kestrel Trading. |

**`data/facts.csv`** (graph edges taken from those chunks. A real system would have an LLM extract them.)
| id | source | relation | target | chunk |
|----|--------|----------|--------|-------|
| F17 | Delta Facility Management | SUBCONTRACTS_TO | Zenith Cleaning Co. | C9 |
| F18 | Zenith Cleaning Co. | PAYS_THROUGH | Harbor Pay Ltd | C10 |
| F19 | Omar Haddad | CONTROLS | Harbor Pay Ltd | C11 |
| F20 | Omar Haddad | SHAREHOLDER_OF | Kestrel Trading | C11 |

**`data/qa_set.json`** (new questions, with gold facts written by hand)
| id | hops | question | gold facts |
|----|------|----------|------------|
| Q6 | 1 | Who does Delta Facility Management subcontract to? | F17 |
| Q7 | 3 | How is Delta Facility Management linked to Omar Haddad? | F17, F18, F19 |
| Q8 | 5 | How is Delta Facility Management linked to OFAC? | F17, F18, F19, F20, F6 |

**`eval_demo.py`**: the question count is no longer hard-coded, the question column is wider, and part 4 also runs Q8.

**`eval_plan_filled.md`**: the group-exercise template filled in for this demo, as a worked example.

## What changes in the output (before → after)

| | demo05 | demo05_new_data |
|---|---|---|
| Data | 7 chunks, 15 facts, 5 questions | 10 chunks, 19 facts, 8 questions |
| Vector RAG recall / fully answerable | 68%, 2/5 | 66%, 3/8 (gets only 20% of Q8) |
| GraphRAG recall / fully answerable | 100%, 5/5 | 100%, 8/8 |
| Part 3 communities | 1 unchanged, 2 changed | 0 unchanged, 3 changed. Delta is now linked to Kestrel, so the graph regroups. |
| Part 4 access control | Q3 only | Q3 **and Q8**. Q8's path needs restricted chunk C10, so only `compliance_officer` sees the link to OFAC. |

The story to tell: a new subcontractor (Delta → Zenith) looks harmless. A restricted bank alert links it through a payment agent to someone tied to a sanctioned company. GraphRAG finds the 5-hop chain. Vector RAG doesn't. Roles without restricted access never see the link.

## How to add your own

1. Add a row to `data/chunks.csv`: `C12,public,"your text"`. Use the next free id. C8 is taken by `new_document.csv`.
2. Add one row per relation to `data/facts.csv`: `F21,Entity A,RELATION,Entity B,C12`. F16 is taken.
3. Add a question to `data/qa_set.json`. Use the exact entity names in it, and list the fact IDs along the path as `gold_facts`.
4. Run `python eval_demo.py`.

---

# Demo 05: Evaluation and production concerns (original notes)

This demo is for **Module 5**. One script covers four production concerns:

| Part | Topic | What you see |
|------|-------|--------------|
| 1 | **Answer quality** (RAGAS-style metrics on a multi-hop QA set) | Vector RAG retrieves 68% of the needed facts, GraphRAG 100%. Vector RAG falls apart from 3 hops on. |
| 2 | **Cost and latency** | Retrieval time, context size and estimated LLM cost per 1,000 questions |
| 3 | **Incremental graph updates** | One new document adds one fact. Only the changed communities are re-summarised, and a new risk link appears. |
| 4 | **Access control and governance** | The same question asked by 3 roles. Restricted facts stay hidden from roles that may not see them, and every question is written to an audit log. |

## Run it

```powershell
cd demo05
python eval_demo.py
```

It needs no API key and no internet.

## Files

| File | Purpose |
|------|---------|
| `eval_demo.py` | The four parts, one function each |
| `data/qa_set.json` | **The multi-hop QA set**: 5 questions (1 to 5 hops), each listing its gold answer and the gold facts needed to answer it |
| `data/facts.csv`, `data/chunks.csv` | The graph facts and their source text. Each chunk has a sensitivity level: public, internal or restricted. |
| `data/new_document.csv` | The document added in part 3 |
| `eval_plan_template.md` | Template for the group exercise |
| `output/audit_log.csv` | Written by part 4 |

## Metrics in one line each

- **Context recall:** did retrieval find all the facts the answer needs? Low recall means the answer will be incomplete.
- **Context precision:** how much of what was retrieved is actually needed? Low precision means noise and extra cost.
- **Faithfulness** (RAGAS): is every claim in the answer supported by the context? It needs an LLM judge; see below.
- **Answer relevancy** (RAGAS): does the answer address the question? It also needs an LLM judge.

This demo computes the first two exactly, because the QA set lists the gold facts for each question. The real **RAGAS** library (`pip install ragas`) computes all four, using an LLM as the judge. It needs a model and an API key, or a local model.

## Group exercise (15 minutes)

In groups of 3–4, fill in `eval_plan_template.md` for a GraphRAG system in your own domain. Each group then presents its plan in 2 minutes.
