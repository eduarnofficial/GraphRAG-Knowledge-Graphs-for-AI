# Evaluation plan: worked example

**System:** GraphRAG over supplier and vendor risk records (this demo's data)
**Team:** Trainer demo

## 1. Test questions
- How many questions? **8 in this demo** (Q1–Q8 in `data/qa_set.json`). In production: 50–100, from real analyst questions plus expert-written multi-hop cases.
- Mix of hop counts: **2** 1-hop (Q1, Q6), **4** 2–3 hops (Q2, Q3, Q4, Q7), **2** 4+ hops (Q5, Q8)
- Who writes the gold answers and gold facts? **A compliance analyst picks the fact IDs from `facts.csv`. A second analyst reviews them.**

## 2. Metrics and targets
| Metric | Target | How measured |
|--------|--------|--------------|
| Context recall | ≥ **95%** | gold facts in QA set (demo: GraphRAG 100%, Vector RAG 66%) |
| Faithfulness | ≥ **90%** | LLM judge (RAGAS) + spot checks of 10 answers a week |
| Answer correctness | ≥ **85%** | expert review of a 20% sample |
| "I don't know" when the answer is missing | **100% of no-answer questions** | e.g. "How is Evergreen Packaging linked to OFAC?" before the C8 update must return "no link" |

## 3. Cost and latency budget
- Max answer time: **5 seconds** (p95)
- Max cost: **$5 per 1,000 questions** (demo estimate: about $2.65)
- Index cost per new document: **1 LLM extraction call + re-summarise only the changed communities**

## 4. Keeping the graph current
- How often do new documents arrive? **Daily (registry filings, bank alerts, approvals).**
- What triggers a re-run of extraction or community summaries? **Every new chunk is extracted on arrival. Communities whose members changed are re-summarised the same night.**
- How do we re-check quality after each update? **Re-run `python eval_demo.py`. New facts get new QA questions (as C9–C11 got Q6–Q8). Recall must not drop below target.**

## 5. Access and governance
- Sensitivity levels in the data: **public, internal, restricted**
- Which roles see what?
  | Role | Sees |
  |------|------|
  | external_auditor | public |
  | analyst | public, internal |
  | compliance_officer | public, internal, restricted |
- What is logged, for how long, and who reviews it? **Time, role, question, facts used and source chunks (`output/audit_log.csv`). Kept 7 years. Reviewed monthly by the compliance lead.**

## 6. Owners
- QA set: **compliance analyst team**
- Graph schema (entity types, relations such as SUBCONTRACTS_TO, PAYS_THROUGH): **data engineering**
- Quality dashboard: **ML / platform team**
