"""Demo 06 (Ollama): one document in, a GraphRAG evaluation out, with a local LLM doing the work.

    1. CHUNK        split the document into chunks                          (plain code)
    2. EXTRACT      read each chunk and write graph facts                   (LLM)
    3. RESOLVE      merge different names for the same entity               (LLM)
    4. GRAPH        build the knowledge graph from the facts                (plain code)
    5. QA SET       write test questions, gold answers and gold facts       (LLM)
    6. ANSWER       answer each question with Vector RAG and with GraphRAG  (LLM; retrieval = embeddings / graph)
    7. JUDGE        grade each answer against the gold answer               (LLM as judge)
    8. SCORE        context recall / precision against the gold facts       (plain code)

Everything runs locally through Ollama (http://localhost:11434). No API key, no cloud.

Command line:   python pipeline.py sample_docs/supplier_risk_report.txt
GUI:            streamlit run app.py
"""
import csv
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import networkx as nx
import requests

HERE = Path(__file__).parent
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
# Speed: how many LLM calls run at the same time. Ollama serves several requests in parallel
# (set OLLAMA_NUM_PARALLEL on the Ollama side to raise its own limit). 1 = one call at a time.
WORKERS = int(os.environ.get("PIPELINE_WORKERS", "1"))   # on CPU, parallel calls only share the cores; use 2-4 on a GPU
CALL_TIMEOUT = int(os.environ.get("PIPELINE_CALL_TIMEOUT", "180"))   # seconds per LLM call before giving up


def parallel(fn, items, progress=None, label=""):
    """Run fn(item) for every item with WORKERS threads; keep the original order.
    progress() is only called from this (main) thread, so Streamlit can update the page safely."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = [None] * len(items)
    if WORKERS <= 1 or len(items) <= 1:
        for i, it in enumerate(items):
            if progress:
                progress(i, len(items), label)
            results[i] = fn(it)
        return results
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fn, it): i for i, it in enumerate(items)}
        for done, fut in enumerate(as_completed(futures)):
            results[futures[fut]] = fut.result()
            if progress:
                progress(done, len(items), label)
    return results


# ----------------------------------------------------------------------------- Ollama
def _tags():
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=5)
        r.raise_for_status()
        return r.json().get("models", [])
    except requests.RequestException:
        return []


def list_models():
    """Names of the models installed in Ollama, or [] if Ollama is not running."""
    return [m["name"] for m in _tags()]


def embedding_models():
    """Installed models that can produce embeddings (e.g. nomic-embed-text). Chat models such as qwen2.5 cannot."""
    out = []
    for m in _tags():
        caps = m.get("capabilities")
        if (caps and "embedding" in caps) or (not caps and "embed" in m["name"]):
            out.append(m["name"])
    return out


# ----------------------------------------------------------------------------- Cohere (cloud, optional)
# Set PIPELINE_PROVIDER=cohere and COHERE_API_KEY=<your key>, or choose Cohere in the GUI.
# Your document is sent to Cohere's servers. Nothing extra to install: plain HTTPS with requests.
PROVIDER = os.environ.get("PIPELINE_PROVIDER", "ollama")          # "ollama" or "cohere"
COHERE_API = "https://api.cohere.com/v2"
COHERE_API_KEY = os.environ.get("COHERE_API_KEY", "")
COHERE_CHAT_MODELS = ["command-r7b-12-2024", "command-r-08-2024", "command-a-03-2025"]   # fastest first
COHERE_EMBED_MODELS = ["embed-english-v3.0", "embed-multilingual-v3.0"]


def _cohere_post(path, body):
    """POST to Cohere with retries: trial keys are rate-limited, so wait and retry on 429 / 5xx."""
    if not COHERE_API_KEY:
        raise RuntimeError("No Cohere API key. Set COHERE_API_KEY or enter it in the GUI sidebar.")
    headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
    for attempt in range(6):
        r = requests.post(f"{COHERE_API}/{path}", json=body, headers=headers, timeout=CALL_TIMEOUT)
        if r.status_code == 429 or r.status_code >= 500:
            wait = float(r.headers.get("Retry-After", 0) or 0) or min(60, 4 * 2 ** attempt)
            time.sleep(wait)
            continue
        if r.status_code == 401:
            raise RuntimeError("Cohere rejected the API key (401). Check the key in the sidebar / COHERE_API_KEY.")
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def cohere_ok():
    """True if the key works (one tiny call)."""
    try:
        _cohere_post("chat", {"model": COHERE_CHAT_MODELS[0], "max_tokens": 1,
                              "messages": [{"role": "user", "content": "hi"}]})
        return True
    except Exception:
        return False


def chat(model, system, user, json_mode=False, temperature=0.0, max_tokens=600):
    """One chat call to the selected provider (Ollama or Cohere). Returns the reply text."""
    if PROVIDER == "cohere":
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        out = _cohere_post("chat", body)
        return "".join(part.get("text", "") for part in out["message"]["content"])
    body = {"model": model, "stream": False, "keep_alive": "30m",
            "options": {"temperature": temperature, "num_ctx": 4096, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["format"] = "json"
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=CALL_TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"]


def chat_json(model, system, user, default, max_tokens=600):
    """Chat call that must return JSON. Small models sometimes wrap or break JSON, so parse leniently."""
    try:
        text = chat(model, system, user, json_mode=True, max_tokens=max_tokens)
    except requests.Timeout:
        # a small model in JSON mode can keep generating forever; skip this call instead of failing the run
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}|\[.*\]", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return default


def embed(model, texts, kind="document"):
    """Embeddings from Ollama (e.g. nomic-embed-text) or Cohere (embed-english-v3.0).
    kind = "document" for chunks, "query" for questions (Cohere uses this to embed them differently)."""
    if PROVIDER == "cohere":
        vecs = []
        for i in range(0, len(texts), 90):            # Cohere accepts up to 96 texts per call
            out = _cohere_post("embed", {"model": model, "texts": texts[i:i + 90], "embedding_types": ["float"],
                                         "input_type": "search_query" if kind == "query" else "search_document"})
            vecs += out["embeddings"]["float"]
        return vecs
    r = requests.post(f"{OLLAMA}/api/embed", json={"model": model, "input": texts}, timeout=600)
    r.raise_for_status()
    return r.json()["embeddings"]


def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def keyword_vectors(texts):
    """Fallback when no embedding model is installed: TF-IDF style word vectors (plain code, no LLM)."""
    docs = [_words(t) for t in texts]
    vocab = sorted({w for d in docs for w in d})
    df = {w: sum(1 for d in docs if w in d) for w in vocab}
    return vocab, df, len(docs)


def keyword_vec(text, vocab, df, n):
    words = _words(text)
    return [words.count(w) * math.log((1 + n) / (1 + df[w])) for w in vocab]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ----------------------------------------------------------------------------- 1. chunk
def chunk_document(text, max_chars=600):
    """Pack whole sentences (and short paragraphs) into chunks of up to max_chars.
    Fewer, fuller chunks = fewer LLM extraction calls, which is what makes a CPU run faster."""
    chunks, current = [], ""
    for para in re.split(r"\n\s*\n", text.strip()):
        for s in re.split(r"(?<=[.!?])\s+", " ".join(para.split())):
            if current and len(current) + len(s) + 1 > max_chars:
                chunks.append(current)
                current = ""
            current = f"{current} {s}".strip()
    if current:
        chunks.append(current)
    return [{"id": f"C{i}", "text": t} for i, t in enumerate(chunks, 1)]


# ----------------------------------------------------------------------------- 2. extract
EXTRACT_SYSTEM = """You extract a knowledge graph from text.
Write one fact per line, in this exact format and nothing else:
source | RELATION | target
Rules:
- One line per relationship stated in the text. Do not invent facts.
- source and target are SHORT names of people, companies, places, courses, exams or things, copied from the text.
  Good: SAA-C03 exam. Bad: learners for the SAA-C03 exam.
- RELATION is UPPER_SNAKE_CASE, e.g. OWNED_BY, DIRECTOR_OF, TEACHES, PREPARES_FOR, LOCATED_IN, ON_LIST.
- Replace pronouns (he, she, it, the company) with the entity they refer to.
Example. Text: "Vinod Kumar teaches the Terraform course. The Terraform course prepares learners for the Terraform Associate exam."
Vinod Kumar | TEACHES | Terraform course
Terraform course | PREPARES_FOR | Terraform Associate exam"""


def _relation(r):
    r = re.sub(r"[^A-Za-z0-9]+", "_", str(r)).strip("_").upper()
    return r or "RELATED_TO"


def extract_facts(chunks, model, progress=None):
    facts = []
    # Plain "source | RELATION | target" lines instead of JSON: about half the tokens to write,
    # and writing tokens is the slow part on a CPU.
    def one(c):
        try:
            return chat(model, EXTRACT_SYSTEM, f"Text:\n{c['text']}", max_tokens=400)
        except requests.Timeout:
            return ""

    outs = parallel(one, chunks, progress, f"Extracting facts from {len(chunks)} chunks")
    for c, out in zip(chunks, outs):
        items = []
        for line in out.splitlines():
            parts = [x.strip(" -*`\"'") for x in line.split("|")]
            if len(parts) == 3 and all(parts):
                items.append({"source": parts[0], "relation": parts[1], "target": parts[2]})
        for f in items if isinstance(items, list) else []:
            if not isinstance(f, dict):
                continue
            s, t = str(f.get("source", "")).strip(), str(f.get("target", "")).strip()
            if s and t and s.lower() != t.lower():
                facts.append({"source": s, "relation": _relation(f.get("relation")), "target": t, "chunk": c["id"]})
    # drop exact duplicates, then number the facts
    seen, unique = set(), []
    for f in facts:
        key = (f["source"].lower(), f["relation"], f["target"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(f)
    for i, f in enumerate(unique, 1):
        f["id"] = f"F{i}"
    return unique


# ----------------------------------------------------------------------------- 3. resolve
STOP = {"the", "of", "and", "a", "an", "for", "in", "on", "at", "to", "co", "ltd", "inc", "pvt", "services", "solutions", "group"}


def _content_words(name):
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in STOP and len(w) > 1}

RESOLVE_SYSTEM = """You clean up entity names in a knowledge graph.
You get a list of entity names. Some are different names for the SAME real-world entity
(e.g. "Ms. Rao" and "Asha Rao", or "Northwind" and "Northwind Holdings").
Return JSON only: {"merge": {"alias name": "canonical name"}}
Only merge names you are sure refer to the same entity. Use the longest, most complete name as canonical.
If nothing should be merged, return {"merge": {}}."""


def resolve_entities(facts, model):
    names = sorted({f[k] for f in facts for k in ("source", "target")})
    if len(names) < 2:
        return facts, {}
    out = chat_json(model, RESOLVE_SYSTEM, "Entities:\n" + "\n".join(f"- {n}" for n in names), {"merge": {}}, max_tokens=300)
    merge = out.get("merge", {}) if isinstance(out, dict) else {}
    lower = {n.lower(): n for n in names}
    # keep only merges between names that really exist, and never chain merges
    mapping = {}
    blocked = {}
    for a, b in merge.items():
        a, b = lower.get(str(a).lower()), lower.get(str(b).lower())
        if not (a and b and a != b):
            continue
        # Guard: small models merge unrelated names (e.g. "EduArn" -> "The Skills Mentorship").
        # Only accept a merge when the two names share a real word.
        if _content_words(a) & _content_words(b):
            mapping[a] = b
        else:
            blocked[a] = b
    # Code rule: "learners for the SAA-C03 exam" -> "SAA-C03 exam" (one name ends with another full name).
    for a in names:
        for b in names:
            if a != b and a not in mapping and len(b) >= 4 and a.lower().endswith(" " + b.lower()):
                mapping[a] = b
                break
    resolve_entities.blocked = blocked
    for f in facts:
        f["source"] = mapping.get(f["source"], f["source"])
        f["target"] = mapping.get(f["target"], f["target"])
    facts = [f for f in facts if f["source"].lower() != f["target"].lower()]
    return facts, mapping


# ----------------------------------------------------------------------------- 4. graph
def build_graph(facts):
    g = nx.MultiGraph()
    for f in facts:
        g.add_edge(f["source"], f["target"], key=f["id"], relation=f["relation"])
    return g


def fact_text(f):
    return f"{f['source']} {f['relation']} {f['target']}"


# ----------------------------------------------------------------------------- 5. QA set
QA_SYSTEM = """You write an evaluation set for a question-answering system over a knowledge graph.
You get numbered facts. Write questions that can be answered ONLY from these facts.
Mix difficulty: some questions need 1 fact, some need a chain of 2 or 3 connected facts (multi-hop),
e.g. "How is A linked to C?" when A-B and B-C are facts.
Return JSON only:
{"questions": [{"question": "...", "gold_answer": "short answer", "gold_facts": ["F1", "F2"]}]}
gold_facts must list EVERY fact id needed to answer, and only those. Use entity names exactly as in the facts."""


def _connected(fids, by_id):
    """True if the gold facts form one connected chain (otherwise it is not a real multi-hop question)."""
    g = nx.Graph()
    for fid in fids:
        f = by_id[fid]
        g.add_edge(f["source"], f["target"])
    return nx.is_connected(g) if g.number_of_nodes() else False


def generate_qa(facts, model, n=6):
    by_id = {f["id"]: f for f in facts}
    listing = "\n".join(f"{f['id']}: {fact_text(f)}" for f in facts)
    out = chat_json(model, QA_SYSTEM, f"Write {n} questions.\nFacts:\n{listing}", {"questions": []})
    items = out.get("questions", []) if isinstance(out, dict) else out
    qa, rejected, seen = [], [], set()
    for q in items if isinstance(items, list) else []:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        fids = [str(x).strip().upper() for x in q.get("gold_facts", []) if str(x).strip().upper() in by_id]
        fids = list(dict.fromkeys(fids))
        item = {"question": str(q["question"]).strip(), "gold_answer": str(q.get("gold_answer", "")).strip(), "gold_facts": fids}
        key = re.sub(r"\W+", " ", item["question"].lower()).strip()
        gold_ents = {by_id[f][k].lower() for f in fids for k in ("source", "target")}
        if key in seen:
            why = "duplicate of an earlier question"
        elif not fids or not _connected(fids, by_id):
            why = "gold facts missing, unknown or not connected"
        elif not item["gold_answer"] or re.fullmatch(r"(F\d+[,\s]*)+", item["gold_answer"].upper()):
            why = "gold answer is empty or just a fact id"
        elif not any(e in item["question"].lower() for e in gold_ents):
            why = "the question names no entity from its own gold facts"
        else:
            why = None
        if why:
            rejected.append({**item, "why": why})
        else:
            seen.add(key)
            qa.append(item)
    for i, q in enumerate(qa, 1):
        q["id"] = f"Q{i}"
        q["hops"] = len(q["gold_facts"])
    return qa, rejected


PATH_QA_SYSTEM = """You turn a chain of knowledge-graph facts into ONE natural test question.
Rules:
- The question must start from the START entity and must be answerable only by following ALL the facts in order.
- The answer to the question is the END entity. Do NOT write the END entity in the question.
- Use entity names exactly as given. One sentence. No fact ids.
Return JSON only: {"question": "..."}"""


def sample_paths(facts, n, max_hops=3, seed=42):
    """Code picks the evidence: connected chains of 1..max_hops facts (random walks that never revisit a node)."""
    import random
    rnd = random.Random(seed)
    adj = {}
    for f in facts:
        adj.setdefault(f["source"], []).append((f["target"], f["id"]))
        adj.setdefault(f["target"], []).append((f["source"], f["id"]))
    nodes = sorted(adj)
    plan = [min(h, max_hops) for h in (1, 2, 3, 2, 3, 1, 3, 2, 3, 3, 2, 1)]
    paths, seen, tries = [], set(), 0
    while len(paths) < n and tries < 3000 and nodes:
        tries += 1
        hops = plan[len(paths) % len(plan)]
        visited, chain = [rnd.choice(nodes)], []
        for _ in range(hops):
            options = [(nb, fid) for nb, fid in adj[visited[-1]] if nb not in visited]
            if not options:
                break
            nb, fid = rnd.choice(options)
            visited.append(nb)
            chain.append(fid)
        if len(chain) == hops and frozenset(chain) not in seen:
            seen.add(frozenset(chain))
            paths.append({"start": visited[0], "end": visited[-1], "facts": chain, "entities": list(visited)})
    return paths


def generate_qa_paths(facts, model, n=6, max_hops=3, progress=None):
    """Path-based QA: code chooses connected fact chains (gold facts + gold answer); the LLM only writes the question."""
    by_id = {f["id"]: f for f in facts}
    qa, rejected = [], []
    paths = sample_paths(facts, n, max_hops)

    def write(p):
        listing = "\n".join(f"{k + 1}. {fact_text(by_id[fid])}" for k, fid in enumerate(p["facts"]))
        return chat_json(model, PATH_QA_SYSTEM,
                         f"START entity: {p['start']}\nEND entity (the answer): {p['end']}\nFacts in order:\n{listing}",
                         {"question": ""}, max_tokens=80)

    outs = parallel(write, paths, progress, f"Writing {len(paths)} questions")
    for p, out in zip(paths, outs):
        question = str(out.get("question", "") if isinstance(out, dict) else "").strip()
        item = {"question": question, "gold_answer": p["end"], "gold_facts": p["facts"]}
        if not question:
            why = "the LLM returned no question"
        elif not any(e.lower() in question.lower() for e in p["entities"] if e != p["end"]):
            why = "question names no entity from its fact chain"
        elif p["end"].lower() in question.lower():
            why = "question gives away the answer"
        elif re.sub(r"\W+", " ", question.lower()).strip() in {re.sub(r"\W+", " ", q["question"].lower()).strip() for q in qa}:
            why = "duplicate of an earlier question"
        else:
            why = None
        if why:
            rejected.append({**item, "why": why})
        else:
            qa.append(item)
    for i, q in enumerate(qa, 1):
        q["id"] = f"Q{i}"
        q["hops"] = len(q["gold_facts"])
    return qa, rejected


# ----------------------------------------------------------------------------- 6. retrieve + answer
class Retrievers:
    """Vector RAG = nearest chunks by embedding. GraphRAG = facts on the paths between the entities in the question."""

    def __init__(self, chunks, facts, embed_model=None, top_k=None):
        """embed_model=None -> keyword similarity instead of embeddings (when no embedding model is installed).
        top_k=None -> retrieve about a third of the chunks (at least 1), so Vector RAG never just returns the whole document."""
        top_k = top_k or max(1, round(len(chunks) / 3))
        self.chunks, self.facts, self.top_k = chunks, facts, top_k
        self.graph = build_graph(facts)
        self.entities = sorted(self.graph.nodes, key=len, reverse=True)
        self.embed_model = embed_model
        texts = [c["text"] for c in chunks]
        if embed_model:
            self.mode = f"embeddings ({embed_model})"
            self.chunk_vecs = embed(embed_model, texts) if chunks else []
        else:
            self.mode = "keyword similarity (no embedding model installed)"
            self.kw = keyword_vectors(texts)
            self.chunk_vecs = [keyword_vec(t, *self.kw) for t in texts]

    def _qvec(self, question):
        return embed(self.embed_model, [question], kind="query")[0] if self.embed_model else keyword_vec(question, *self.kw)

    def vector(self, question):
        qv = self._qvec(question)
        ranked = sorted(zip(self.chunks, self.chunk_vecs), key=lambda cv: cosine(qv, cv[1]), reverse=True)
        top = [c for c, _ in ranked[: self.top_k]]
        ids = {c["id"] for c in top}
        return {"context": "\n".join(f"[{c['id']}] {c['text']}" for c in top),
                "chunks": [c["id"] for c in top],
                "facts": [f["id"] for f in self.facts if f["chunk"] in ids]}

    def link(self, question):
        """Entity linking: entity names that appear in the question (longest first)."""
        found, text = [], question.lower()
        for e in self.entities:
            if e.lower() in text and not any(e.lower() in x.lower() for x in found):
                found.append(e)
        return found

    def graph_rag(self, question, max_hops=5):
        ents = self.link(question)
        g, used = self.graph, []
        simple = nx.Graph(g)
        if len(ents) >= 2:                       # connect every pair of linked entities
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    try:
                        path = nx.shortest_path(simple, ents[i], ents[j])
                    except nx.NetworkXNoPath:
                        continue
                    if len(path) - 1 <= max_hops:
                        for a, b in zip(path, path[1:]):
                            used += [k for k in g[a][b]]
        elif ents:                                # one entity: its direct neighbourhood
            for nb in g[ents[0]]:
                used += [k for k in g[ents[0]][nb]]
        used = list(dict.fromkeys(used))
        by_id = {f["id"]: f for f in self.facts}
        return {"context": "\n".join(f"[{fid}] {fact_text(by_id[fid])}" for fid in used),
                "entities": ents, "facts": used}


ANSWER_SYSTEM = """Answer the question using ONLY the context. Be short (1-2 sentences).
If the context does not contain the answer, say exactly: "I don't know from the context." """


def answer(model, question, context):
    if not context.strip():
        return "I don't know from the context."
    return chat(model, ANSWER_SYSTEM, f"Context:\n{context}\n\nQuestion: {question}", max_tokens=120).strip()


# ----------------------------------------------------------------------------- 7. judge
JUDGE_SYSTEM = """You grade answers. You get a question, the correct (gold) answer, the retrieved context and a system's answer.
Return JSON only: {"correct": 0 or 1, "faithful": 0 or 1, "reason": "one short sentence"}
correct = 1 if the answer gives the same key information as the gold answer (wording may differ).
faithful = 1 if every claim in the answer is supported by the context (an "I don't know" answer is faithful)."""


def judge(model, q, ans, context):
    out = chat_json(model, JUDGE_SYSTEM,
                    f"Question: {q['question']}\nGold answer: {q['gold_answer']}\nContext:\n{context or '(empty)'}\nAnswer: {ans}",
                    {"correct": 0, "faithful": 0, "reason": "judge returned no JSON"}, max_tokens=80)
    def bit(v):
        try:
            return 1 if float(v) >= 0.5 else 0
        except (TypeError, ValueError):
            return 1 if str(v).strip().lower() in ("yes", "true") else 0
    return {"correct": bit(out.get("correct")), "faithful": bit(out.get("faithful")), "reason": str(out.get("reason", ""))}


# ----------------------------------------------------------------------------- 8. score
def context_scores(gold, got):
    gold, got = set(gold), set(got)
    recall = len(gold & got) / len(gold) if gold else 0.0
    precision = len(gold & got) / len(got) if got else 0.0
    return round(recall, 2), round(precision, 2)


def evaluate(qa, retr, model, progress=None, use_judge=True):
    def one(q):
        row = {"id": q["id"], "hops": q["hops"], "question": q["question"], "gold_answer": q["gold_answer"], "gold_facts": q["gold_facts"]}
        for name, fn in (("vector", retr.vector), ("graph", retr.graph_rag)):
            t0 = time.perf_counter()
            r = fn(q["question"])
            ans = answer(model, q["question"], r["context"])
            secs = time.perf_counter() - t0
            rec, prec = context_scores(q["gold_facts"], r["facts"])
            j = judge(model, q, ans, r["context"]) if use_judge else {"correct": 0, "faithful": 0, "reason": "judge switched off"}
            row[name] = {"answer": ans, "context": r["context"], "facts": r["facts"], "recall": rec, "precision": prec,
                         "correct": j["correct"], "faithful": j["faithful"], "judge_reason": j["reason"], "seconds": round(secs, 1)}
        return row

    return parallel(one, qa, progress, f"Answering{' and judging' if use_judge else ''} {len(qa)} questions")


def summary(rows):
    out = {}
    for name in ("vector", "graph"):
        n = len(rows) or 1
        out[name] = {
            "context_recall": round(sum(r[name]["recall"] for r in rows) / n, 2),
            "context_precision": round(sum(r[name]["precision"] for r in rows) / n, 2),
            "correct": sum(r[name]["correct"] for r in rows),
            "faithful": sum(r[name]["faithful"] for r in rows),
            "questions": len(rows),
        }
    return out


# ----------------------------------------------------------------------------- save (same file formats as demo05)
def save_run(run_dir, chunks, facts, qa, rejected, rows, meta):
    run_dir = Path(run_dir)
    (run_dir / "data").mkdir(parents=True, exist_ok=True)
    with open(run_dir / "data" / "chunks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "sensitivity", "text"])
        w.writerows([[c["id"], "public", c["text"]] for c in chunks])
    with open(run_dir / "data" / "facts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "source", "relation", "target", "chunk"])
        w.writerows([[x["id"], x["source"], x["relation"], x["target"], x["chunk"]] for x in facts])
    (run_dir / "data" / "qa_set.json").write_text(json.dumps(
        [{"id": q["id"], "hops": q["hops"], "question": q["question"], "gold_facts": q["gold_facts"], "gold_answer": q["gold_answer"]} for q in qa],
        indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "rejected_questions.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps({"meta": meta, "summary": summary(rows), "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_dir


CACHE = HERE / "output" / "cache"


def _cache_key(text, model, chunk_chars):
    import hashlib
    return hashlib.sha1(f"{model}|{chunk_chars}|{text}".encode("utf-8")).hexdigest()[:16]


def run_all(text, model=DEFAULT_MODEL, embed_model="auto", n_questions=6, chunk_chars=600, progress=None, qa_mode="paths", use_judge=True, use_cache=True):
    """qa_mode="paths": code picks connected fact chains and the LLM phrases the questions (reliable).
       qa_mode="free":  the LLM writes questions, answers and gold facts on its own (shows what goes wrong)."""
    """The whole pipeline. progress(step_name, i, n, message) is called as it goes (used by the GUI)."""
    if embed_model == "auto":
        found = COHERE_EMBED_MODELS if PROVIDER == "cohere" else embedding_models()
        embed_model = found[0] if found else None
    def p(step):
        return (lambda i, n, msg: progress(step, i, n, msg)) if progress else None
    t0 = time.perf_counter()
    timings, mark = {}, [time.perf_counter()]

    def lap(name):
        now = time.perf_counter()
        timings[name] = round(now - mark[0], 1)
        mark[0] = now

    chunks = chunk_document(text, chunk_chars)
    # Cache: the same document + model + chunk size reuses the extracted facts, so re-runs
    # (other QA mode, fewer questions, judge off) skip the slowest step entirely.
    key = _cache_key(text, model, chunk_chars)
    cache_file = CACHE / f"{key}.json"
    cached = use_cache and cache_file.exists()
    if cached:
        c = json.loads(cache_file.read_text(encoding="utf-8"))
        facts, merged, blocked = c["facts"], c["merged"], c.get("blocked", {})
        if progress:
            progress("extract", 0, 1, "Using cached facts for this document (no LLM calls)")
        lap("extract + resolve (cached)")
    else:
        facts = extract_facts(chunks, model, p("extract"))
        lap("extract facts")
        if progress:
            progress("resolve", 0, 1, "Merging duplicate entity names")
        facts, merged = resolve_entities(facts, model)
        blocked = getattr(resolve_entities, "blocked", {})
        for i, f in enumerate(facts, 1):         # renumber after merges removed self-loops
            f["id"] = f"F{i}"
        lap("merge names")
        CACHE.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"facts": facts, "merged": merged, "blocked": blocked}, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress("qa", 0, 1, "Writing the QA set")
    if qa_mode == "free":
        qa, rejected = generate_qa(facts, model, n_questions)
    else:
        qa, rejected = generate_qa_paths(facts, model, n_questions, progress=p("qa"))
    lap("write QA set")
    if progress:
        progress("index", 0, 1, "Embedding chunks for Vector RAG")
    retr = Retrievers(chunks, facts, embed_model)
    lap("embed chunks")
    rows = evaluate(qa, retr, model, p("evaluate"), use_judge)
    lap("answer" + (" + judge" if use_judge else ""))
    meta = {"provider": PROVIDER, "model": model, "embed_model": embed_model, "vector_mode": retr.mode, "created": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(time.perf_counter() - t0, 1), "merged_entities": merged,
            "merges_blocked": blocked, "qa_mode": qa_mode, "timings": timings, "cached_facts": cached,
            "judge": use_judge, "workers": WORKERS}
    return {"chunks": chunks, "facts": facts, "qa": qa, "rejected": rejected, "rows": rows, "meta": meta, "retr": retr}


# ----------------------------------------------------------------------------- command line
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    doc = Path(args[0]) if args else HERE / "sample_docs" / "supplier_risk_report.txt"
    if PROVIDER == "cohere":
        model = os.environ.get("COHERE_MODEL", COHERE_CHAT_MODELS[0])
        emb = [os.environ.get("COHERE_EMBED_MODEL", COHERE_EMBED_MODELS[0])]
        if not COHERE_API_KEY:
            sys.exit("Set your key first:  $env:COHERE_API_KEY = \"...\"")
        print(f"Provider: Cohere (cloud) - the document is sent to Cohere")
    else:
        model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        if model not in list_models():
            sys.exit(f"Ollama is not running or model '{model}' is not installed. Try:  ollama pull {model}")
        emb = embedding_models()
    print(f"Document: {doc.name}   Model: {model}   Vector RAG: {emb[0] if emb else 'keyword similarity (ollama pull nomic-embed-text for embeddings)'}\n")
    qa_mode = "free" if "--free" in sys.argv else "paths"
    res = run_all(doc.read_text(encoding="utf-8"), model, embed_model=emb[0] if emb else None,
                  qa_mode=qa_mode, use_judge="--no-judge" not in sys.argv,
                  use_cache="--no-cache" not in sys.argv,
                  progress=lambda step, i, n, msg: print(f"  [{step}] {msg} ({i + 1}/{n})"))
    out = save_run(HERE / "output" / datetime.now().strftime("run_%Y%m%d_%H%M%S"),
                   res["chunks"], res["facts"], res["qa"], res["rejected"], res["rows"], res["meta"])
    s = summary(res["rows"])
    print(f"\n{len(res['chunks'])} chunks, {len(res['facts'])} facts, {len(res['qa'])} questions "
          f"({len(res['rejected'])} rejected), {res['meta']['seconds']} s")
    print(f"\n  {'system':<10}{'recall':>8}{'precision':>11}{'correct':>9}{'faithful':>10}")
    for name, label in (("vector", "Vector RAG"), ("graph", "GraphRAG")):
        x = s[name]
        print(f"  {label:<10}{x['context_recall']:>8.0%}{x['context_precision']:>11.0%}"
              f"{x['correct']:>6}/{x['questions']}{x['faithful']:>7}/{x['questions']}")
    print("\nTime per step: " + ", ".join(f"{k} {v}s" for k, v in res["meta"]["timings"].items()))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
