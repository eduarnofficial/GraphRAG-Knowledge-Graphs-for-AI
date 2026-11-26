"""Demo 06 (Ollama) GUI.   Run:  streamlit run app.py

Upload one document. A local Ollama model extracts the facts, writes the QA set,
answers with Vector RAG and GraphRAG, and judges the answers. Everything stays on your machine.
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import pipeline as pl

HERE = Path(__file__).parent
SAMPLE = HERE / "sample_docs" / "supplier_risk_report.txt"

st.set_page_config(page_title="GraphRAG with Ollama or Cohere", page_icon="🕸️", layout="wide")
st.title("🕸️ GraphRAG: one document, everything done by the LLM (Ollama or Cohere)")
st.caption("Chunk → extract facts (LLM) → merge names (LLM) → graph → QA set (LLM) → answer with Vector RAG and GraphRAG (LLM) → judge (LLM) → scores")

# ----------------------------------------------------------------------------- sidebar
KEYWORD = "Keyword similarity (no embedding model)"
with st.sidebar:
    st.header("LLM provider")
    provider = st.radio("Where the LLM runs", ["Ollama (local, private)", "Cohere (cloud, faster)"],
                        index=1 if pl.PROVIDER == "cohere" else 0)
    if provider.startswith("Cohere"):
        pl.PROVIDER = "cohere"
        key = st.text_input("Cohere API key", value=pl.COHERE_API_KEY, type="password",
                            help="From dashboard.cohere.com → API keys. Only the key is needed, never your password. "
                                 "It stays in this browser session; or set the COHERE_API_KEY environment variable before starting.")
        pl.COHERE_API_KEY = key.strip()
        if not pl.COHERE_API_KEY:
            st.info("Enter your Cohere API key to continue.")
            st.stop()
        st.warning("Cloud mode: your document is sent to Cohere. Use Ollama for private documents.")
        model = st.selectbox("LLM (extraction, QA, answers, judge)", pl.COHERE_CHAT_MODELS,
                             help="command-r7b is the fastest and cheapest; command-a is the strongest.")
        embed_choice = st.selectbox("Vector RAG retrieval", pl.COHERE_EMBED_MODELS + [KEYWORD])
        embed_model = None if embed_choice == KEYWORD else embed_choice
    else:
        pl.PROVIDER = "ollama"
        models = pl.list_models()
        if not models:
            st.error(f"Ollama is not reachable at {pl.OLLAMA}. Start Ollama and pull a model, e.g.\n\n`ollama pull qwen2.5:1.5b`")
            st.stop()
        st.success(f"Ollama connected · {len(models)} model(s)")
        emb_installed = pl.embedding_models()
        chat_models = [m for m in models if m not in emb_installed] or models
        model = st.selectbox("LLM (extraction, QA, answers, judge)", chat_models,
                             index=chat_models.index(pl.DEFAULT_MODEL) if pl.DEFAULT_MODEL in chat_models else 0)
        embed_choice = st.selectbox("Vector RAG retrieval", emb_installed + [KEYWORD],
                                    help="Vector RAG needs an embedding model. Chat models like qwen2.5 cannot embed. "
                                         "Install one with: ollama pull nomic-embed-text")
        embed_model = None if embed_choice == KEYWORD else embed_choice
        if embed_model is None:
            st.info("No embedding model installed, so Vector RAG uses keyword similarity. "
                    "For real embeddings run `ollama pull nomic-embed-text` and reload.")
    st.header("Settings")
    qa_choice = st.radio("How to write the QA set",
                         ["Path-based: code picks fact chains, LLM writes the question",
                          "Free-form: the LLM decides everything"],
                         help="Free-form shows what goes wrong when a small LLM writes its own test set "
                              "(fact ids as answers, duplicates, gold facts that do not connect). "
                              "Path-based fixes it: the gold facts and gold answer come from the graph.")
    qa_mode = "free" if qa_choice.startswith("Free") else "paths"
    n_questions = st.slider("Questions to generate", 3, 12, 6)
    st.header("Speed")
    use_cache = st.toggle("Reuse facts already extracted from this document", value=True,
                          help="Extraction is the slowest step. With this on, running the same document again "
                               "(e.g. to switch QA mode or turn the judge off) skips it. Switch off to extract again.")
    use_judge = st.toggle("LLM judge (correct / faithful)", value=True,
                          help="Switch off to roughly halve the answering time. Recall and precision are still computed exactly.")
    chunk_chars = st.slider("Max characters per chunk", 200, 1500, 600, step=50,
                            help="Bigger chunks = fewer extraction calls = faster, but a small model may miss facts in long chunks.")
    pl.WORKERS = st.slider("Parallel LLM calls", 1, 8, 3 if pl.PROVIDER == "cohere" else 1,
                           help="Cohere: 3-4 is much faster (a trial key is rate-limited; the app waits and retries). "
                                "Ollama on CPU: keep 1, parallel calls just share the same cores. "
                                "Ollama on a GPU: set OLLAMA_NUM_PARALLEL=4 and use 2-4 here.")
    st.caption("Fastest on CPU: fewer questions, bigger chunks, judge off.")
    st.caption("Bigger models (qwen2.5:7b, llama3.1:8b) extract facts and write questions far more reliably than 1.5B models.")

# ----------------------------------------------------------------------------- document
st.subheader("1. Your document")
up = st.file_uploader("Upload a .txt or .md file", type=["txt", "md"])
if up is not None:
    default_text = up.read().decode("utf-8", errors="replace")
else:
    default_text = SAMPLE.read_text(encoding="utf-8")
text = st.text_area("Document text (edit freely)", default_text, height=220)

run = st.button("▶ Run the full pipeline with Ollama", type="primary", disabled=not text.strip())

if run:
    steps = {"extract": "Extracting facts", "resolve": "Merging names", "qa": "Writing QA set",
             "index": "Embedding chunks", "evaluate": "Answering & judging"}
    bar = st.progress(0.0, text="Starting…")
    order = list(steps)

    def progress(step, i, n, msg):
        base = order.index(step) / len(order)
        bar.progress(min(1.0, base + (i / max(n, 1)) / len(order)), text=f"{steps[step]}: {msg}")

    with st.status("Running the pipeline on your local LLM…", expanded=True) as status:
        try:
            res = pl.run_all(text, model, embed_model, n_questions, chunk_chars, progress, qa_mode, use_judge, use_cache)
        except Exception as e:  # show Ollama errors (e.g. model not able to embed) in the page
            status.update(label="Failed", state="error")
            st.exception(e)
            st.stop()
        run_dir = pl.save_run(HERE / "output" / datetime.now().strftime("run_%Y%m%d_%H%M%S"),
                              res["chunks"], res["facts"], res["qa"], res["rejected"], res["rows"], res["meta"])
        res["run_dir"] = str(run_dir)
        st.session_state["res"] = res
        bar.progress(1.0, text="Done")
        st.write("**Time per step:** " + " · ".join(f"{k} {v}s" for k, v in res["meta"]["timings"].items()))
        if res["meta"].get("cached_facts"):
            st.write("Facts came from the cache (extraction skipped). Switch off *Reuse facts* in the sidebar to extract again.")
        status.update(label=f"Done in {res['meta']['seconds']} s · saved to {run_dir.name}", state="complete")

res = st.session_state.get("res")
if not res:
    st.info("Press **Run** to let the LLM process the document. The sample document is a supplier risk report with multi-hop links.")
    st.stop()

# ----------------------------------------------------------------------------- results
s = pl.summary(res["rows"])
st.subheader("2. Results")
c = st.columns(6)
c[0].metric("Chunks", len(res["chunks"]))
c[1].metric("Facts (LLM)", len(res["facts"]))
c[2].metric("Questions (LLM)", len(res["qa"]), help=f"{len(res['rejected'])} rejected by validation")
c[3].metric("GraphRAG recall", f"{s['graph']['context_recall']:.0%}",
            f"{(s['graph']['context_recall'] - s['vector']['context_recall']) * 100:+.0f} pts vs vector")
c[4].metric("GraphRAG correct", f"{s['graph']['correct']}/{s['graph']['questions']}")
c[5].metric("Vector RAG correct", f"{s['vector']['correct']}/{s['vector']['questions']}")

tabs = st.tabs(["📊 Scores", "🧩 Chunks", "🔗 Facts", "🕸️ Graph", "❓ QA set", "💬 Answers", "🔍 Ask your own", "📁 Files"])

with tabs[0]:
    df = pd.DataFrame([
        {"System": "Vector RAG", "Context recall": s["vector"]["context_recall"], "Context precision": s["vector"]["context_precision"],
         "Correct (LLM judge)": f"{s['vector']['correct']}/{s['vector']['questions']}", "Faithful (LLM judge)": f"{s['vector']['faithful']}/{s['vector']['questions']}"},
        {"System": "GraphRAG", "Context recall": s["graph"]["context_recall"], "Context precision": s["graph"]["context_precision"],
         "Correct (LLM judge)": f"{s['graph']['correct']}/{s['graph']['questions']}", "Faithful (LLM judge)": f"{s['graph']['faithful']}/{s['graph']['questions']}"},
    ])
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"Context recall": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0f%%"),
                                "Context precision": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0f%%")})
    per_q = pd.DataFrame([{"Q": r["id"], "Hops": r["hops"], "Vector recall": r["vector"]["recall"], "Graph recall": r["graph"]["recall"]} for r in res["rows"]])
    if not per_q.empty:
        st.caption("Context recall per question: GraphRAG keeps up as questions need more hops; Vector RAG usually drops.")
        st.bar_chart(per_q.set_index("Q")[["Vector recall", "Graph recall"]], stack=False)
    st.caption("Context recall/precision are computed exactly from the gold facts. Correct/faithful come from the LLM judge, "
               "so with a small model treat them as indicative, not exact.")

with tabs[1]:
    st.dataframe(pd.DataFrame(res["chunks"]), hide_index=True, use_container_width=True)

with tabs[2]:
    st.dataframe(pd.DataFrame(res["facts"])[["id", "source", "relation", "target", "chunk"]] if res["facts"] else pd.DataFrame(),
                 hide_index=True, use_container_width=True)
    if res["meta"]["merged_entities"]:
        st.write("**Names merged (LLM + code rule):**", res["meta"]["merged_entities"])
    if res["meta"].get("merges_blocked"):
        st.warning("**Merges the LLM suggested but the guard blocked** (the names share no real word):")
        st.write(res["meta"]["merges_blocked"])

with tabs[3]:
    if res["facts"]:
        dot = ["graph G {", 'graph [rankdir=LR, bgcolor="transparent"];',
               'node [shape=box, style="rounded,filled", fillcolor="#e0f2fe", color="#0369a1", fontname="Helvetica"];',
               'edge [color="#64748b", fontname="Helvetica", fontsize=10];']
        for f in res["facts"]:
            a, b, r = (x.replace('"', "'") for x in (f["source"], f["target"], f["relation"]))
            dot.append(f'"{a}" -- "{b}" [label="{r} ({f["id"]})"];')
        dot.append("}")
        st.graphviz_chart("\n".join(dot), use_container_width=True)
    else:
        st.warning("The LLM extracted no facts. Try a bigger model.")

with tabs[4]:
    mode = res["meta"].get("qa_mode", "paths")
    st.caption("Mode: **path-based** (gold facts and gold answer chosen by code from the graph; LLM wrote the wording)"
               if mode == "paths" else "Mode: **free-form** (the LLM wrote questions, answers and gold facts itself)")
    st.dataframe(pd.DataFrame([{"id": q["id"], "hops": q["hops"], "question": q["question"], "gold_answer": q["gold_answer"],
                                "gold_facts": ", ".join(q["gold_facts"])} for q in res["qa"]]), hide_index=True, use_container_width=True)
    if res["rejected"]:
        with st.expander(f"{len(res['rejected'])} question(s) the LLM wrote but validation rejected"):
            st.json(res["rejected"])

with tabs[5]:
    for r in res["rows"]:
        with st.expander(f"{r['id']} ({r['hops']} hop{'s' if r['hops'] != 1 else ''}): {r['question']}"):
            st.write(f"**Gold answer:** {r['gold_answer']}  ·  **Gold facts:** {', '.join(r['gold_facts'])}")
            a, b = st.columns(2)
            for col, name, label in ((a, "vector", "Vector RAG"), (b, "graph", "GraphRAG")):
                x = r[name]
                col.markdown(f"**{label}** · recall {x['recall']:.0%} · {'✅ correct' if x['correct'] else '❌ wrong'} · "
                             f"{'faithful' if x['faithful'] else '⚠️ not faithful'} · {x['seconds']} s")
                col.info(x["answer"])
                col.caption(f"Judge: {x['judge_reason']}")
                col.code(x["context"] or "(no context retrieved)", language=None)

with tabs[6]:
    q = st.text_input("Ask a question about the document", "How is Orion Retail Group linked to the EU sanctions list?")
    if st.button("Ask both systems") and q.strip():
        retr = res["retr"]
        a, b = st.columns(2)
        for col, label, fn in ((a, "Vector RAG", retr.vector), (b, "GraphRAG", retr.graph_rag)):
            with col, st.spinner(f"{label} is answering…"):
                r = fn(q)
                col.markdown(f"**{label}**" + (f" · linked entities: {', '.join(r['entities'])}" if r.get("entities") else ""))
                col.info(pl.answer(model, q, r["context"]))
                col.code(r["context"] or "(no context retrieved)", language=None)

with tabs[7]:
    st.write(f"Saved in `{res['run_dir']}` in the same formats as demo05, so you can compare them with the hand-written files there.")
    d = Path(res["run_dir"])
    for name in ("data/chunks.csv", "data/facts.csv", "data/qa_set.json", "results.json"):
        p = d / name
        if p.exists():
            st.download_button(f"⬇ {name}", p.read_bytes(), file_name=p.name, key=name)
