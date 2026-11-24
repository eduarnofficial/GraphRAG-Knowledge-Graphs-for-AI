# Demo 04: GraphRAG retrieval patterns

This demo is for **Module 4**. One script shows four ways to retrieve from a graph:

| Part | Pattern | One-line idea |
|------|---------|---------------|
| A | **Microsoft GraphRAG**: communities, summaries, local vs global search | Group connected entities and write a summary per group. **Local** search starts from one entity. **Global** search reads the group summaries. |
| B | **Hybrid** vector + graph | Vector search finds the best chunk, then the graph adds the facts connected to it |
| C | **Text-to-Cypher** | An English question becomes a database query, which then runs |
| D | **Multi-hop traversal** | Follow links across documents to find a hidden connection |

## Run it

```powershell
cd demo04
python graphrag_demo.py
```

It needs no API key and no internet, and uses the packages already installed for demos 01–03.

## Lab: run local and global queries

```powershell
python graphrag_demo.py local "Who is Viktor Petrov connected to?"
```
```powershell
python graphrag_demo.py local "Who owns Evergreen Packaging?"
```
```powershell
python graphrag_demo.py global "What are the main risks in our vendor base?"
```
```powershell
python graphrag_demo.py cypher "Who approved Delta Facility Management?"
```

**Try this:**
1. Ask global search about one specific person. What goes wrong?
2. Ask local search a "big picture" question. What goes wrong?
3. **Lesson:** use local search for questions about specific entities, and global search for questions about themes across the whole dataset.

## Settings in `config.json`

| Setting | Options | Meaning |
|---------|---------|---------|
| `engine` | `mini` (default), `microsoft` | `mini` is the built-in GraphRAG. `microsoft` calls the real Microsoft GraphRAG CLI; see `ms_graphrag/README.md`. |
| `llm` | `offline` (default), `ollama`, `claude` | `offline` builds answers from templates. `ollama` uses a free LLM running on your own machine. `claude` uses the Anthropic API (run `pip install anthropic` and set an API key first). Each LLM writes the summaries, the answers and the text-to-Cypher queries. |
| `ollama_model` | `qwen2.5:1.5b` | Any model you have pulled with Ollama |

### Using Ollama (free and local)

```powershell
ollama run qwen2.5:1.5b
```

Run that once to download the model; Ollama keeps serving it in the background. Then set `"llm": "ollama"` in `config.json` and run the demo as usual. The full run takes about 100 seconds on a laptop CPU.

**Teaching point:** a 1.5B model is small. In testing it:
- reversed a fact ("Orion Ventures, which is owned by Evergreen Packaging")
- added risks that aren't in the data ("insider trading")
- wrote a Cypher query in the wrong direction, which returned **nothing** without an error

The demo flags that empty result (`WARNING: the LLM's query returned no rows`). All three are good examples for Module 5 (evaluation): bigger models make fewer of these mistakes, and every LLM answer needs checking against the graph.

If the chosen engine or LLM isn't available, the script says so and uses the offline version, so the demo never fails in class.

## How the mini engine maps to Microsoft GraphRAG

| Microsoft GraphRAG | This demo |
|--------------------|-----------|
| Leiden community detection | Louvain community detection, built into networkx |
| LLM-written community reports | A template summary, or Claude when `llm` is `claude` |
| Local search: entities, their neighbours and source text units | `local_search()`: the entities named in the question, their facts and their source chunks |
| Global search: a map-reduce over community reports | `global_search()`: score each report (map), then combine the best ones (reduce) |
