# Evaluation plan: group exercise

**System:** ______________________ (for example "GraphRAG over supplier contracts")
**Team:** ______________________

## 1. Test questions
- How many questions? From where? (real user logs, experts, generated)
- Mix of hop counts: ___ 1-hop, ___ 2–3 hops, ___ 4+ hops
- Who writes the gold answers and gold facts?

## 2. Metrics and targets
| Metric | Target | How measured |
|--------|--------|--------------|
| Context recall | ≥ ___% | gold facts in QA set |
| Faithfulness | ≥ ___% | LLM judge (RAGAS) + spot checks |
| Answer correctness | ≥ ___% | expert review of a sample |
| "I don't know" when the answer is missing | ___ | questions with no answer in the data |

## 3. Cost and latency budget
- Max answer time: ___ seconds (p95)
- Max cost: ___ per 1,000 questions
- Index cost per new document: ___

## 4. Keeping the graph current
- How often do new documents arrive?
- What triggers a re-run of extraction or community summaries?
- How do we re-check quality after each update? (re-run the QA set)

## 5. Access and governance
- Sensitivity levels in the data: ______________________
- Which roles see what?
- What is logged, for how long, and who reviews it?

## 6. Owners
- Who owns the QA set, the graph schema and the quality dashboard?
