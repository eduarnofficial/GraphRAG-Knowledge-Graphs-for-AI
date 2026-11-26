# Demo 06 (Ollama): one document in, everything done by a local LLM

In demo06 every file was **written by hand**: the chunks, the graph facts and the QA set with its gold answers.
In this demo you drop in **one document** and a local model running in **Ollama** does all of that work itself,
then answers the questions with Vector RAG and GraphRAG and grades its own answers. No API key, no internet, no cloud.

| Step | Who does it | Output |
|------|-------------|--------|
| 1. Chunk the document | plain code (split on paragraphs) | `data/chunks.csv` |
| 2. Extract graph facts from each chunk | **LLM** | `data/facts.csv` |
| 3. Merge different names for the same entity | **LLM** | merges shown in the GUI |
| 4. Build the knowledge graph | plain code (NetworkX) | graph picture in the GUI |
| 5. Write test questions, gold answers and gold facts | **LLM** (validated by code) | `data/qa_set.json` |
| 6. Answer each question: Vector RAG and GraphRAG | **LLM** (retrieval: embeddings / graph paths) | `results.json` |
| 7. Judge each answer: correct? faithful? | **LLM as judge** | `results.json` |
| 8. Context recall and precision | plain code, exact, using the gold facts | scores |

The output files use the **same format as demo05**, so you can put them side by side with the hand-written ones.

## Set up (once)

1. Install Ollama from https://ollama.com and pull a model:

   ```powershell
   ollama pull qwen2.5:1.5b
   ```

   Optional but recommended: a real embedding model for Vector RAG, and a bigger LLM for better extraction:

   ```powershell
   ollama pull nomic-embed-text
   ollama pull qwen2.5:7b
   ```

2. Create the Python environment and install the packages:

   ```powershell
   cd C:\AI-ML\GraphRAG-Course\demo06_ollama
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

## Run the GUI (Streamlit)

```powershell
cd C:\AI-ML\GraphRAG-Course\demo06_ollama
.venv\Scripts\streamlit run app.py
```

It opens in your browser at http://localhost:8501.

1. In the sidebar, pick the **LLM** and the **embedding model**.
2. Upload a `.txt` / `.md` file, or keep the sample supplier risk report.
3. Press **Run the full pipeline with Ollama** and watch each step.
4. Explore the tabs: **Scores**, **Chunks**, **Facts**, **Graph**, **QA set**, **Answers** (both systems side by side with the judge's verdict), **Ask your own**, **Files** (download).

## Run from the command line

```powershell
.venv\Scripts\python pipeline.py sample_docs\supplier_risk_report.txt
```

Each run is saved in `output\run_<date>_<time>\`.

To use another model: `$env:OLLAMA_MODEL = "qwen2.5:7b"` before running.

## What to show and discuss

- **Compare with demo05.** Open the generated `facts.csv` and `qa_set.json` next to the hand-written ones. Which facts did the LLM miss or invent? Are its gold answers right?
- **Model size matters.** A 1.5B model misses relations, names entities inconsistently and sometimes writes questions whose gold facts do not connect (the code rejects those; see "rejected" in the QA tab). Re-run with `qwen2.5:7b` and compare.
- **The judge is also an LLM.** Recall and precision are exact. "Correct" and "faithful" come from the same small model, so they can be wrong. This is why real projects keep a human-checked QA set.
- **Multi-hop questions.** The sample document hides a 4-hop chain: Orion Retail Group → Bluefin Motors → Calder Industries → Elena Varga → Mistral Shipping (EU sanctions). Ask it in the **Ask your own** tab and compare the two systems.

## Faster: run it on Cohere (cloud) instead of Ollama

On a CPU-only laptop a 1.5B model writes about 9 tokens per second, so a run takes minutes.
Cohere runs the same steps on cloud GPUs in seconds. Same pipeline, same files; only the provider changes.

| | Ollama | Cohere |
|---|---|---|
| Where it runs | your machine | Cohere's cloud |
| Your document | never leaves the machine | **is sent to Cohere** |
| Speed on a CPU laptop | minutes | seconds |
| Cost | free | free trial key (rate-limited), then paid |
| Models | `qwen2.5:1.5b`, `qwen2.5:7b`, … | `command-r7b-12-2024` (fastest), `command-r-08-2024`, `command-a-03-2025` (strongest); embeddings `embed-english-v3.0` |

1. Get an API key at https://dashboard.cohere.com → **API keys**. Only the key is needed, never your account password.
2. **GUI:** sidebar → *Cohere (cloud, faster)* → paste the key into the password box. Set *Parallel LLM calls* to 3–4.
3. **Command line:**

   ```powershell
   $env:PIPELINE_PROVIDER = "cohere"
   $env:COHERE_API_KEY = "paste-your-key-here"
   $env:PIPELINE_WORKERS = "3"
   .venv\Scripts\python pipeline.py sample_docs\eduarn_training_platform.txt
   ```

   Optional: `$env:COHERE_MODEL = "command-a-03-2025"` for the strongest model.

Keep the key out of code and out of git. A trial key allows only a limited number of calls per minute;
the pipeline waits and retries automatically when Cohere answers "429 Too Many Requests".

**Good classroom comparison:** run the same document on `qwen2.5:1.5b` (local) and on `command-a-03-2025` (cloud),
then compare the Facts tab and the QA set. Model quality changes the graph more than any prompt tweak.

## Classroom demo: how to make LLM-written test questions good (about 20 minutes)

The point to land: **an LLM can help write an evaluation set, but code and humans must control the gold answers.**
Use `sample_docs/eduarn_training_platform.txt` (or the supplier report) and walk through four rounds.

**Round 1: let the LLM do everything (the problem).** Sidebar → *Free-form*, then Run. Open the **QA set** tab and ask the group what is wrong:

| What you will typically see | Why it happens |
|---|---|
| Gold answers like `F2`, `F4` instead of a name | the model copied the fact id instead of answering |
| The same question many times | small models repeat themselves |
| Most questions rejected (e.g. 11 of 14) | gold facts that do not connect, or questions that do not mention their own facts |
| Vague questions ("What is the course prepared by Vinod Kumar?") | two correct answers exist; the model picked one |

Then open the **Facts** tab: look for names that were merged wrongly (the guard now lists blocked merges, e.g. *EduArn → The Skills Mentorship*)
and entities that should be one node but are two (*"learners for the SAA-C03 exam"* vs *"SAA-C03 exam"*). Bad facts mean bad questions.

**Round 2: let code pick the evidence (the fix).** Sidebar → *Path-based*, Run again.
Code walks the graph and picks connected chains of 1–3 facts. The **gold facts and the gold answer come from the graph**, so they are always valid.
The LLM only does what it is good at: turning the chain into a natural question. Code still checks that the question names the start entity and does not give away the answer.

**Round 3: a bigger model.** Pull `qwen2.5:7b` and pick it in the sidebar. Compare the **Facts** count and the number of rejected questions with the 1.5B run.

**Round 4: human review (what production teams do).** Download `qa_set.json` from the **Files** tab and have the group fix one wrong gold answer and delete one unfair question.
Reviewed questions become the fixed regression test you re-run after every change, as in demo05.

**Discussion questions**
- Why must the judge's "correct" score be checked by a human, when recall and precision need no LLM at all?
- Which step did most of the damage: extraction, name merging or question writing? How would you measure it?
- Free-form questions can test things the graph missed. Why might you still keep a few of them, after human review?

The same comparison from the command line:

```powershell
.venv\Scripts\python pipeline.py sample_docs\eduarn_training_platform.txt --free
.venv\Scripts\python pipeline.py sample_docs\eduarn_training_platform.txt
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit GUI |
| `pipeline.py` | All the steps; also runs from the command line |
| `sample_docs/supplier_risk_report.txt` | Sample document with multi-hop links |
| `requirements.txt` | streamlit, networkx, requests, pandas |
| `output/run_*/` | One folder per run: `data/chunks.csv`, `data/facts.csv`, `data/qa_set.json`, `results.json`, `rejected_questions.json` |
