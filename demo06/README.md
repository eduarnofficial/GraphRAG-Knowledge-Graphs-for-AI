# Demo 06: Capstone, a mini GraphRAG Q&A

This is the capstone for **Module 6**. One script builds a GraphRAG Q&A system end to end on a **new domain** (medication safety) and compares it against vector-only RAG.

| Stage | Steps | Module it comes from |
|-------|-------|----------------------|
| **Build** | 6 documents, then 14 extracted facts, then names resolved ("Ms. Rao" = "Asha Rao"), then a graph | Modules 2–3 |
| **Answer** | GraphRAG (entity linking + multi-hop paths) compared with vector-only RAG | Modules 1, 4 |
| **Evaluate** | Context recall and precision on a 4-question multi-hop QA set | Module 5 |

## Run it

```powershell
cd demo06
python capstone.py
```

**Result:** GraphRAG finds **100%** of the needed facts and fully answers 4 of 4 questions. Vector RAG finds **64%** and fully answers 1 of 4.

## Ask your own questions

```powershell
python capstone.py ask "Why is Ibuprofen risky for Chen Li?"
```

To let a local LLM write the final answer from the GraphRAG facts, add `--ollama` (Ollama must be running with `qwen2.5:1.5b`):

```powershell
python capstone.py ask "Why is Ibuprofen risky for Chen Li?" --ollama
```

**Watch the answer.** In testing, the small model wrote that Chen Li takes Warfarin "to treat Osteoarthritis", which is not in the facts. This is a live example of a faithfulness failure (Module 5): the retrieval was right, but the generation still made something up.

## Capstone tasks for learners (pick one)

1. **Add a document.** Add a new note to `corpus/` and its facts to `sample_extractions.json`, then re-run. Do the answers change?
2. **Add a question.** Add a 4-hop question with its gold facts to `qa_set.json`. Which system breaks first?
3. **Break resolution.** Rename "Ms. Rao" to "Mrs. A. Rao" in the extractions. What happens to recall, and why?

## Files

| File | Purpose |
|------|---------|
| `capstone.py` | The whole pipeline, with one section each for building, answering and evaluating |
| `corpus/*.txt` | 6 short documents: patient notes, drug labels, a policy and a clinic roster |
| `sample_extractions.json` | Extracted facts, deliberately with messy names |
| `qa_set.json` | 4 test questions (1 to 3 hops) and their gold facts |
