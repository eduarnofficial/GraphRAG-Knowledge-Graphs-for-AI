# Optional: run the real Microsoft GraphRAG

The built-in `mini` engine in `graphrag_demo.py` teaches the same ideas and needs no installation or API key. Use this folder only if you want to show the real tool.

`input/acme_documents.txt` holds the same 7 short texts as the demo.

## Steps

Microsoft GraphRAG needs Python 3.10–3.12 and an LLM API key (OpenAI by default).

```powershell
pip install graphrag
```
```powershell
graphrag init --root ms_graphrag
```
This creates `settings.yaml` and `.env`. Put your key in `ms_graphrag\.env` as `GRAPHRAG_API_KEY=...`.

```powershell
graphrag index --root ms_graphrag
```
This builds entities, communities and community reports into `ms_graphrag\output\`. It calls the LLM many times, so it costs money and takes a few minutes.

Then run the two kinds of search:
```powershell
graphrag query "Who is Viktor Petrov connected to?" --root ms_graphrag --method local
```
```powershell
graphrag query "What are the main risks in our vendor base?" --root ms_graphrag --method global
```

## Use it from the demo

In `config.json`, set `"engine": "microsoft"`. `graphrag_demo.py local ...` and `graphrag_demo.py global ...` will then call the real CLI. If `graphrag` isn't installed or the folder isn't indexed yet, the demo says so and uses the mini engine instead.

## Notes

- **Other model providers.** GraphRAG calls models through LiteLLM, so you can point it at other providers in `settings.yaml`. The model must support structured JSON output. See the configuration docs at microsoft.github.io/graphrag.
- **Ollama instead of OpenAI.** You can point `settings.yaml` at your local Ollama server (`http://localhost:11434`). You need both a chat model, such as `qwen2.5:1.5b`, and an embedding model, for example `ollama pull nomic-embed-text`. Use the provider names and fields from the `settings.yaml` that `graphrag init` generates; I haven't tested this setup. A 1.5B model is likely too small for GraphRAG's extraction step. Expect weak or failed indexing, and try a 7B or larger model if your machine can run one. The built-in demo's `"llm": "ollama"` mode works with `qwen2.5:1.5b` and was tested.
- **Not tested here.** These commands follow the current GraphRAG documentation, but they were not run on this machine because it has no OpenAI key.
