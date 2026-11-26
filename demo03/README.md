# Demo 03: Building a knowledge graph from text

This demo is for **Module 3**. It uses one script and three short documents to show four steps:

| Step | What happens | Why it matters |
|------|--------------|----------------|
| 1. **Chunk** | Split each document into pieces of 2 sentences | An LLM extracts facts more reliably from short text, and each fact remembers which chunk it came from |
| 2. **Extract** | An LLM returns the entities and relations it finds, as JSON | Turns prose into graph facts, using only the types allowed by the Module 2 schema |
| 3. **Resolve** | "Petrov", "V. Petrov" and "Viktor Petrov" become one person | Without this step the facts never connect. The demo shows **0 paths** without it. |
| 4. **Load** | `MERGE` the facts into a graph database, then ask a multi-hop question | The answer is a 5-hop path across 3 documents |

## Run it

```powershell
cd demo03
python build_kg.py
```

This runs **offline**. Instead of calling an LLM, it reads `sample_extractions.json`, a hand-written example of the JSON an LLM returns. No API key is needed.

To use a real LLM (Claude) for step 2:

```powershell
pip install anthropic
python build_kg.py --live
```

`--live` needs an Anthropic API key, either from the `ANTHROPIC_API_KEY` environment variable or from `ant auth login`. Each chunk is one API call, so a run makes 6 calls.

To use a free local LLM through Ollama instead:

```powershell
ollama run qwen2.5:1.5b
```
```powershell
python build_kg.py --ollama
```

The first command downloads the model; Ollama then keeps serving it in the background. The demo asks Ollama to return the same JSON schema as Claude, and a run takes about 80 seconds on a laptop. If Ollama isn't running, the demo uses `sample_extractions.json` instead. To try another model, change `OLLAMA_MODEL` at the top of `build_kg.py`.

### Guard rail: the schema check

After extraction, every relation is checked against the Module 2 rules. For example, `DIRECTOR_OF` must go from a Person to a Company. Anything else is printed as `REJECTED` and kept out of the graph.

**Teaching point:** with the small `qwen2.5:1.5b` model, the check rejected **5 of 10** extracted facts. One example was "Viktor Petrov OWNED_BY Kestrel Trading": a person cannot be owned. The model also reversed an ownership and missed the shared address. The remaining facts were too few to connect the documents, so the multi-hop question found **no path**, and the script says so. Compare that with the clean sample extraction, which finds 2 paths. Extraction quality decides what the graph can answer. That is why we validate with the schema, check sources, and measure quality (Module 5).

## Files

| File | Purpose |
|------|---------|
| `corpus/*.txt` | 3 short documents: a news article, a company registry extract and an email |
| `build_kg.py` | The whole pipeline, with one commented section per step |
| `sample_extractions.json` | Example LLM output for offline mode. The names in it are deliberately messy. |

## Lab (15 minutes): extract and load your own document

1. Add a new file to `corpus/`, for example `corpus/board_minutes.txt`:
   `Maria Lopez is also a director of Orion Ventures. Orion Ventures owns Evergreen Packaging Ltd.`
2. Add its facts to the graph in one of two ways:
   - **Offline:** act as the LLM. Add a `"board_minutes#1"` entry to `sample_extractions.json` in the same format as the others.
  "entities": [
    {"name": "Maria Lopez", "type": "Person"},
    {"name": "Orion Ventures", "type": "Company"},
    {"name": "Evergreen Packaging Ltd", "type": "Company"}
  ],
  "relations": [
    {"source": "Maria Lopez", "relation": "DIRECTOR_OF", "target": "Orion Ventures"},
    {"source": "Orion Ventures", "relation": "OWNS", "target": "Evergreen Packaging Ltd"}
  ]
  },
   - **Live:** run `python build_kg.py --live`. Claude extracts the facts for you.
3. Run the script again and check:
   - Did "Evergreen Packaging Ltd" and "Orion Ventures" get new nodes?
   - Did step 3 merge any names?
   - Is Evergreen Packaging now linked to the sanctions list? **Yes**, 6 hops away: Maria Lopez also sits on Silverline's board. One new document changed the risk picture.

**Discussion:** What should happen when the LLM extracts a fact that is wrong? Who reviews it? (Hint: the schema from Module 2 rejects unknown types, and every fact keeps its source chunk, so someone can check it.)
