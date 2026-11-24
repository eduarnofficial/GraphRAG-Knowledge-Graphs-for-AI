# Demo 05: Evaluation and production concerns

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
