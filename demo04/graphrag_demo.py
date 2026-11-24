"""Module 4 demo - GraphRAG retrieval patterns, one small script.

    A. Microsoft GraphRAG ideas: communities -> community summaries -> LOCAL vs GLOBAL search
    B. Hybrid retrieval: vector search finds a chunk, the graph adds what is connected to it
    C. Text-to-Cypher: a question in English becomes a database query
    D. Multi-hop traversal: follow links across documents

Run everything:          python graphrag_demo.py
Lab - your own question: python graphrag_demo.py local  "Who is Viktor Petrov?"
                         python graphrag_demo.py global "What are the main risks in our vendor base?"
                         python graphrag_demo.py cypher "Who approved Cobalt IT Services?"

Settings live in config.json:
    engine: mini | microsoft     (microsoft = real Microsoft GraphRAG, if installed and indexed)
    llm:    offline | ollama | claude   (ollama = free local LLM; claude = Anthropic API; offline = no LLM)
Anything missing (package, index, API key) falls back to the local offline version.
"""
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import kuzu
import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8-sig"))   # -sig: also accepts files saved by Notepad


def read(name):
    with open(HERE / "data" / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


CHUNKS = {r["id"]: r["text"] for r in read("chunks")}
TYPES = {r["name"]: r["type"] for r in read("entities")}
FACTS = read("facts")


# -----------------------------------------------------------------------------
# Optional LLM. Returns None when offline or unavailable, so callers fall back.
# -----------------------------------------------------------------------------
def llm(prompt):
    if CONFIG["llm"] == "ollama":
        return ollama(prompt)
    if CONFIG["llm"] != "claude":
        return None
    try:
        import anthropic
        response = anthropic.Anthropic().beta.messages.create(
            model=CONFIG["model"], max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return None
        return next(b.text for b in response.content if b.type == "text").strip()
    except Exception as e:                       # no package, no key, no network ...
        print(f"  (LLM unavailable: {type(e).__name__} - using offline answer)")
        return None


def ollama(prompt):
    """Local LLM through Ollama's REST API (start it with:  ollama run qwen2.5:1.5b).
    Uses only Python's standard library, so there is nothing extra to install."""
    import urllib.request
    body = json.dumps({"model": CONFIG.get("ollama_model", "qwen2.5:1.5b"),
                       "messages": [{"role": "user", "content": prompt}],
                       "stream": False, "options": {"temperature": 0}}).encode()
    request = urllib.request.Request(CONFIG.get("ollama_url", "http://localhost:11434") + "/api/chat",
                                     data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())["message"]["content"].strip()
    except Exception as e:                       # Ollama not running, model not pulled ...
        print(f"  (Ollama unavailable: {type(e).__name__} - using offline answer)")
        return None


# -----------------------------------------------------------------------------
# The graph, twice: networkx for communities, Kùzu for Cypher queries
# -----------------------------------------------------------------------------
G = nx.Graph()
for f in FACTS:
    G.add_edge(f["source"], f["target"], rel=f["relation"], chunk=f["chunk"])


def fact_text(a, b):
    """Edge as a readable fact, in its real direction."""
    f = next(x for x in FACTS if {x["source"], x["target"]} == {a, b})
    return f"{f['source']} {f['relation']} {f['target']}"


def open_kuzu():
    path = HERE / "output" / "kg"
    path.parent.mkdir(exist_ok=True)
    # start clean: remove the database AND its .wal log file (a leftover log would replay old tables)
    for old in path.parent.glob(path.name + "*"):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    conn = kuzu.Connection(kuzu.Database(str(path)))
    conn.execute("CREATE NODE TABLE Entity(name STRING, type STRING, PRIMARY KEY(name))")
    conn.execute("CREATE REL TABLE RELATED(FROM Entity TO Entity, type STRING, chunk STRING)")
    for name, etype in TYPES.items():
        conn.execute("CREATE (:Entity {name: $n, type: $t})", {"n": name, "t": etype})
    for f in FACTS:
        conn.execute("""MATCH (a:Entity {name: $s}), (b:Entity {name: $t})
                        CREATE (a)-[:RELATED {type: $r, chunk: $c}]->(b)""",
                     {"s": f["source"], "t": f["target"], "r": f["relation"], "c": f["chunk"]})
    return conn


def cypher(conn, query):
    result = conn.execute(query)
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return rows


def mentioned(question):
    """Entity linking: which graph entities does the question name?"""
    q = question.lower()
    return [n for n in TYPES if n.lower() in q or re.search(rf"\b{re.escape(n.split()[0].lower())}\b", q)]


# =============================================================================
# A. MICROSOFT GRAPHRAG IDEAS
# =============================================================================
# A1. Communities: groups of entities that are densely linked to each other.
#     Microsoft GraphRAG uses the Leiden algorithm; we use Louvain (built into networkx).
#     resolution < 1 gives fewer, bigger communities (here: 3 clear themes).
COMMUNITIES = sorted(nx.community.louvain_communities(G, seed=7, resolution=0.5), key=len, reverse=True)


# A2. Community summaries: a short report per community, written ONCE at index time.
def summarise(i, members):
    sub = G.subgraph(members)
    facts = sorted((fact_text(a, b) for a, b in sub.edges), key=lambda f: ("SANCTIONS" not in f, f))  # risk facts first
    hub = max(members, key=lambda n: sub.degree(n))
    flags = [m for m in members if TYPES[m] == "SanctionsList"]
    text = llm("Write a 2-sentence risk summary of this group of related facts for a compliance officer:\n" + "\n".join(facts))
    if text is None:   # offline template
        text = (f"Centred on {hub}. Key facts: {'; '.join(facts[:4])}."
                + (f" RISK: the group includes a sanctions list ({', '.join(flags)})." if flags else " No sanctions exposure found."))
    return {"id": i, "title": f"{hub} cluster", "members": sorted(members), "summary": text, "risk": bool(flags)}


SUMMARIES = [summarise(i, m) for i, m in enumerate(COMMUNITIES, 1)]


# A3. LOCAL search: start from the entities named in the question, collect their
#     neighbourhood (facts + the original text chunks), answer from that.
def local_search(question):
    if CONFIG["engine"] == "microsoft" and (answer := microsoft_query(question, "local")):
        return answer
    seeds = mentioned(question)
    if not seeds:
        return "No known entity in the question. (Local search needs a starting entity - try global search.)"
    edges = {tuple(sorted(e)) for s in seeds for e in G.edges(s)}
    facts = sorted(fact_text(a, b) for a, b in edges)
    chunks = sorted({G.edges[a, b]["chunk"] for a, b in edges})
    context = "FACTS:\n" + "\n".join(facts) + "\nSOURCE TEXT:\n" + "\n".join(f"[{c}] {CHUNKS[c]}" for c in chunks)
    answer = llm(f"Answer using only this context.\n{context}\nQUESTION: {question}")
    return answer or f"Starting from {', '.join(seeds)}:\n    " + "\n    ".join(facts) + f"\n    Sources: {', '.join(chunks)}"


# A4. GLOBAL search: no starting entity. MAP over every community summary
#     (which ones are relevant?), then REDUCE them into one answer.
def global_search(question):
    if CONFIG["engine"] == "microsoft" and (answer := microsoft_query(question, "global")):
        return answer
    def words(text):   # lowercase words, plural "s" removed, common words dropped
        return {w.rstrip("s") for w in re.findall(r"[a-z]+", text.lower())} - {"the", "what", "are", "in", "our", "of", "a", "i", "main"}
    q = words(question)
    scored = []
    for s in SUMMARIES:                                            # MAP: how relevant is each report?
        score = len(q & words(s["summary"])) + (3 if s["risk"] and "risk" in q else 0)
        scored.append((score, s))
    top = [s for score, s in sorted(scored, key=lambda x: -x[0]) if score > 0][:3]
    if not top:
        return ("No community report matches this question. Global search only reads the short summaries, "
                "so details about one entity are lost - use LOCAL search for that.")
    reports = "\n".join(f"- {s['title']}: {s['summary']}" for s in top)
    answer = llm(f"Combine these community reports into one answer.\n{reports}\nQUESTION: {question}")   # REDUCE
    return answer or f"Based on {len(top)} of {len(SUMMARIES)} community reports:\n" + reports


def microsoft_query(question, method):
    """Real Microsoft GraphRAG CLI, if installed and indexed. Otherwise None (fall back to mini)."""
    root = HERE / CONFIG["ms_graphrag_root"]
    if not shutil.which("graphrag") or not (root / "output").exists():
        print("  (Microsoft GraphRAG not installed or not indexed - using the built-in mini version)")
        return None
    run = subprocess.run(["graphrag", "query", question, "--root", str(root), "--method", method],
                         capture_output=True, text=True)
    return run.stdout.strip() or None


# =============================================================================
# B. HYBRID: vector search finds the entry point, the graph expands it
# =============================================================================
def hybrid_search(question):
    ids = list(CHUNKS)
    vec = TfidfVectorizer(stop_words="english").fit([CHUNKS[i] for i in ids] + [question])
    sims = cosine_similarity(vec.transform([question]), vec.transform([CHUNKS[i] for i in ids]))[0]
    best = ids[sims.argmax()]
    in_chunk = [n for n in TYPES if n in CHUNKS[best]]
    extra = sorted({fact_text(a, b) for n in in_chunk for a, b in G.edges(n)
                    if G.edges[a, b]["chunk"] != best})
    return best, in_chunk, extra


# =============================================================================
# C. TEXT-TO-CYPHER: English question -> Cypher query -> run it
# =============================================================================
SCHEMA = ("Node: Entity(name, type) where type is Vendor, Company, Person, Address or SanctionsList. "
          "Relationship: (:Entity)-[:RELATED {type, chunk}]->(:Entity) where type is OWNED_BY, DIRECTOR_OF, "
          "APPROVED, REGISTERED_AT or ON_SANCTIONS_LIST. This is Kùzu Cypher.")


EXAMPLE = ("Question: Who approved Apex Logistics?\n"
           "Cypher: MATCH (p:Entity)-[r:RELATED {type: 'APPROVED'}]->(v:Entity {name: 'Apex Logistics'}) RETURN p.name")


def text_to_cypher(question):
    """Ask the LLM for a query: schema + one worked example + the exact entity names (helps small models)."""
    generated = llm(f"{SCHEMA}\nEntity names: {', '.join(TYPES)}\n\n{EXAMPLE}\n\n"
                    f"Question: {question}\nWrite ONE read-only Cypher query. Return only the query.")
    if generated:
        fenced = re.search(r"```(?:cypher)?\s*(.*?)```", generated, re.S)        # strip ``` code fences
        query = (fenced.group(1) if fenced else generated).strip()
        return query.removeprefix("Cypher:").strip().rstrip(";")
    return template_cypher(question)


def template_cypher(question):
    """Offline stand-in for the LLM: a few question patterns -> query templates."""
    q, names = question.lower(), mentioned(question)
    if "approv" in q and names and TYPES[names[0]] == "Person":
        return f"MATCH (p:Entity {{name: '{names[0]}'}})-[r:RELATED {{type: 'APPROVED'}}]->(v:Entity) RETURN v.name"
    if "approv" in q and names:
        return f"MATCH (p:Entity)-[r:RELATED {{type: 'APPROVED'}}]->(v:Entity {{name: '{names[0]}'}}) RETURN p.name"
    if ("own" in q or "control" in q) and names:
        return f"MATCH (a:Entity {{name: '{names[0]}'}})-[:RELATED*1..4]->(o:Entity {{type: 'Company'}}) RETURN DISTINCT o.name"
    if "director" in q and names:
        return f"MATCH (p:Entity {{type: 'Person'}})-[r:RELATED {{type: 'DIRECTOR_OF'}}]->(c:Entity {{name: '{names[0]}'}}) RETURN p.name"
    return "MATCH (v:Entity {type: 'Vendor'}) RETURN v.name"


def safe(query):
    """Never run an LLM-written query that could change the data."""
    return not re.search(r"\b(CREATE|MERGE|DELETE|SET|DROP|REMOVE|COPY)\b", query, re.I)


def ask_graph(conn, question):
    """Text-to-Cypher with guard rails: block writes, and if the LLM's query fails, use the template."""
    query = text_to_cypher(question)
    if not safe(query):
        return query, "REFUSED: the query is not read-only"
    try:
        rows = [r[0] for r in cypher(conn, query)]
        if not rows and query != template_cypher(question):
            # A wrong query often runs fine and returns NOTHING - the most dangerous failure.
            check = [r[0] for r in cypher(conn, template_cypher(question))]
            print(f"  WARNING: the LLM's query returned no rows. The template query returns {check} - check the LLM's query.")
        return query, rows
    except Exception as e:
        print(f"  LLM query failed ({str(e).splitlines()[0][:90]}) - using the template query instead")
        query = template_cypher(question)
        return query, [r[0] for r in cypher(conn, query)]


# =============================================================================
# D. MULTI-HOP TRAVERSAL
# =============================================================================
# Follow only "control" links. "The same employee approved both vendors" is not a risk link.
MULTI_HOP = """MATCH (v:Entity {type: 'Vendor'})-[r:RELATED* SHORTEST 1..6 (e, n | WHERE e.type <> 'APPROVED')]-(s:Entity {type: 'SanctionsList'})
RETURN v.name, length(r), properties(nodes(r), 'name')"""


def banner(t):
    print("\n" + "=" * 90 + f"\n{t}\n" + "=" * 90)


if __name__ == "__main__":
    print(f"engine = {CONFIG['engine']}   llm = {CONFIG['llm']}   ({len(TYPES)} entities, {len(FACTS)} facts, {len(CHUNKS)} chunks)")
    conn = open_kuzu()
    mode, question = (sys.argv[1], " ".join(sys.argv[2:])) if len(sys.argv) > 2 else (None, None)

    if mode == "local":
        print(local_search(question)); sys.exit()
    if mode == "global":
        print(global_search(question)); sys.exit()
    if mode == "cypher":
        query, result = ask_graph(conn, question)
        print(query); print(result); sys.exit()

    banner("A1  COMMUNITIES  (groups of densely connected entities)")
    for s in SUMMARIES:
        print(f"  Community {s['id']}: {', '.join(s['members'])}")

    banner("A2  COMMUNITY SUMMARIES  (written once, at index time)")
    for s in SUMMARIES:
        print(f"  [{s['title']}]{'  <-- RISK' if s['risk'] else ''}\n    {s['summary']}")

    banner("A3  LOCAL SEARCH  - a question about a specific entity")
    q = "Who is Viktor Petrov connected to?"
    print(f"  Q: {q}\n  {local_search(q)}")

    banner("A4  GLOBAL SEARCH  - a question about the whole dataset")
    q = "What are the main risks in our vendor base?"
    print(f"  Q: {q}\n  {global_search(q)}")

    banner("B   HYBRID  - vector search picks the chunk, the graph adds connected facts")
    q = "Which vendor shares an office with a sanctioned company?"
    best, ents, extra = hybrid_search(q)
    print(f"  Q: {q}\n  Vector search -> chunk {best}: \"{CHUNKS[best]}\"")
    print(f"  Entities in that chunk: {', '.join(ents)}")
    print("  Graph adds facts from OTHER chunks:\n    " + "\n    ".join(extra))

    banner("C   TEXT-TO-CYPHER  - English in, database query out")
    for q in ["Who approved Cobalt IT Services?", "Which companies control Apex Logistics?"]:
        query, result = ask_graph(conn, q)
        print(f"  Q: {q}\n  Cypher: {query}\n  Result: {result}\n")

    banner("D   MULTI-HOP TRAVERSAL  - shortest path from each vendor to a sanctions list")
    for vendor, hops, via in cypher(conn, MULTI_HOP):
        print(f"  {vendor}  ({hops} hops)  via {' -> '.join(via)}")
