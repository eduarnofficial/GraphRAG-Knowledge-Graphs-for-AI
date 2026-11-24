"""Module 3 demo - build a knowledge graph from plain text in 4 steps.

    STEP 1  CHUNK     split each document into small pieces
    STEP 2  EXTRACT   an LLM reads each chunk and returns entities + relations as JSON
    STEP 3  RESOLVE   merge different names for the same thing ("Petrov" = "V. Petrov")
    STEP 4  LOAD      write the clean facts into a graph database, then ask a question

Run:
    python build_kg.py           offline: uses sample_extractions.json (no API key needed)
    python build_kg.py --live    real LLM: calls Claude for every chunk (needs an API key)
    python build_kg.py --ollama  free local LLM via Ollama (first run once:  ollama run qwen2.5:1.5b)
"""
import json
import re
import shutil
import sys
from pathlib import Path

import kuzu

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
LIVE = "--live" in sys.argv
OLLAMA = "--ollama" in sys.argv
OLLAMA_MODEL = "qwen2.5:1.5b"                  # any model you have pulled with Ollama
OLLAMA_URL = "http://localhost:11434/api/chat"

# The allowed types come from the Module 2 schema. The LLM must stick to them.
ENTITY_TYPES = ["Person", "Company", "Address", "SanctionsList"]
RELATION_TYPES = ["OWNED_BY", "DIRECTOR_OF", "APPROVED", "REGISTERED_AT", "ON_SANCTIONS_LIST"]

# Domain -> range rules from the Module 2 schema: which entity types each relation may connect.
RULES = {"OWNED_BY": ("Company", "Company"), "DIRECTOR_OF": ("Person", "Company"),
         "APPROVED": ("Person", "Company"), "REGISTERED_AT": ("Company", "Address"),
         "ON_SANCTIONS_LIST": ("Company", "SanctionsList")}


# =============================================================================
# STEP 1 - CHUNK: split text into pieces of 2 sentences
# =============================================================================
# Why? LLMs extract more reliably from short text, and each fact keeps a
# "source" (which chunk it came from) so answers can cite their evidence.
def chunk(doc_name, text, sentences_per_chunk=2):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return [{"id": f"{doc_name}#{i // sentences_per_chunk + 1}",
             "text": " ".join(sentences[i:i + sentences_per_chunk])}
            for i in range(0, len(sentences), sentences_per_chunk)]


# =============================================================================
# STEP 2 - EXTRACT: the LLM turns text into JSON facts
# =============================================================================
PROMPT = f"""Extract a knowledge graph from the text.
Entity types allowed: {", ".join(ENTITY_TYPES)}.
Relation types allowed: {", ".join(RELATION_TYPES)}.
Write names exactly as they appear in the text. Only extract facts the text states."""

# A JSON schema forces the answer into exactly this shape.
SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "type": {"type": "string", "enum": ENTITY_TYPES}},
            "required": ["name", "type"], "additionalProperties": False}},
        "relations": {"type": "array", "items": {
            "type": "object",
            "properties": {"source": {"type": "string"},
                           "relation": {"type": "string", "enum": RELATION_TYPES},
                           "target": {"type": "string"}},
            "required": ["source", "relation", "target"], "additionalProperties": False}},
    },
    "required": ["entities", "relations"], "additionalProperties": False,
}


def extract_with_claude(text):
    """Real LLM call: one chunk in, validated JSON out."""
    import anthropic                                   # only needed for --live
    client = anthropic.Anthropic()                     # reads ANTHROPIC_API_KEY
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        system=PROMPT,
        messages=[{"role": "user", "content": text}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],     # if the model declines, retry on a fallback model
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        return {"entities": [], "relations": []}
    return json.loads(next(b.text for b in response.content if b.type == "text"))


SAMPLE = json.loads((HERE / "sample_extractions.json").read_text(encoding="utf-8"))


def extract_with_ollama(text):
    """Free local LLM. Ollama's 'format' option forces the reply into the same JSON schema."""
    import urllib.request
    body = json.dumps({"model": OLLAMA_MODEL, "stream": False, "format": SCHEMA, "options": {"temperature": 0},
                       "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}]}).encode()
    request = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(json.loads(response.read())["message"]["content"])


def extract(chunk_):
    if LIVE:
        return extract_with_claude(chunk_["text"])
    if OLLAMA:
        try:
            return extract_with_ollama(chunk_["text"])
        except Exception as e:                 # Ollama not running, model not pulled ...
            print(f"  (Ollama unavailable: {type(e).__name__} - using sample_extractions.json for {chunk_['id']})")
    return SAMPLE.get(chunk_["id"], {"entities": [], "relations": []})


# =============================================================================
# STEP 3 - RESOLVE: one real-world thing = one node
# =============================================================================
# The LLM writes names as they appear, so the same company shows up as
# "Kestrel Trading FZE" and "Kestrel Trading". Without this step the graph
# would hold two disconnected nodes and the multi-hop path would break.
LEGAL_SUFFIXES = {"ltd", "limited", "fze", "inc", "plc", "llc"}


def tokens(name):
    words = re.sub(r"[^\w\s]", " ", name.lower()).split()
    return [w for w in words if w not in LEGAL_SUFFIXES and w != "s"]


def same_entity(short, long):
    """True if every word of the short name matches the long name (an initial counts: V = Viktor)."""
    s, l = tokens(short), tokens(long)
    return len(s) <= len(l) and all(any(w == x or (len(w) == 1 and x.startswith(w)) for x in l) for w in s)


def resolve(entities):
    """Map every raw name to one canonical name (the longest version seen)."""
    canonical = {}
    by_type = {}
    for e in entities:
        by_type.setdefault(e["type"], set()).add(e["name"])
    for etype, names in by_type.items():
        for name in sorted(names, key=len, reverse=True):          # longest names first
            match = [c for c in set(canonical.values()) if by_type_of(c, by_type) == etype and same_entity(name, c)]
            canonical[name] = match[0] if len(match) == 1 else name
    return canonical


def by_type_of(name, by_type):
    return next(t for t, names in by_type.items() if name in names)


# =============================================================================
# STEP 4 - LOAD: write nodes and links into a graph database (Kùzu, Cypher)
# =============================================================================
# One generic table for entities and one for relations: LLM output can contain
# any allowed type, so the type is stored as a property.
def load(entities, relations, canonical, db_name="kg_from_text"):
    db_path = HERE / "output" / db_name
    db_path.parent.mkdir(exist_ok=True)
    # start clean: remove the database AND its .wal log file (a leftover log would replay old tables)
    for old in db_path.parent.glob(db_path.name + "*"):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    conn = kuzu.Connection(kuzu.Database(str(db_path)))
    conn.execute("CREATE NODE TABLE Entity(name STRING, type STRING, PRIMARY KEY(name))")
    conn.execute("CREATE REL TABLE RELATED(FROM Entity TO Entity, type STRING, source STRING)")
    for e in entities:
        # MERGE = create only if missing, so duplicates collapse into one node
        conn.execute("MERGE (n:Entity {name: $name}) ON CREATE SET n.type = $type",
                     {"name": canonical[e["name"]], "type": e["type"]})
    for r in relations:
        conn.execute("""MATCH (a:Entity {name: $s}), (b:Entity {name: $t})
                        MERGE (a)-[:RELATED {type: $rel, source: $src}]->(b)""",
                     {"s": canonical[r["source"]], "t": canonical[r["target"]], "rel": r["relation"], "src": r["chunk"]})
    return conn


def rows(result):
    out = []
    while result.has_next():
        out.append(result.get_next())
    return out


if __name__ == "__main__":
    mode = ("LIVE - calling Claude" if LIVE else f"OLLAMA - local model {OLLAMA_MODEL}" if OLLAMA
            else "OFFLINE - using sample_extractions.json")
    print(f"MODE: {mode}\n")

    print("STEP 1  CHUNK")
    chunks = []
    for path in sorted((HERE / "corpus").glob("*.txt")):
        chunks += chunk(path.stem, path.read_text(encoding="utf-8"))
    for c in chunks:
        print(f"  [{c['id']}] {c['text']}")

    print("\nSTEP 2  EXTRACT  (LLM output, one chunk at a time)")
    entities, relations = [], []
    for c in chunks:
        result = extract(c)
        entities += result["entities"]
        relations += [{**r, "chunk": c["id"]} for r in result["relations"]]
        for r in result["relations"]:
            print(f"  [{c['id']}] ({r['source']})-[:{r['relation']}]->({r['target']})")

    # Real LLMs sometimes use a name in a relation without listing it as an entity.
    # Add it, borrowing the type of a matching known name (default: Company).
    known = {e["name"]: e["type"] for e in entities}
    for r in relations:
        for name in (r["source"], r["target"]):
            if name not in known:
                match = next((t for k, t in known.items() if same_entity(name, k) or same_entity(k, name)), "Company")
                known[name] = match
                entities.append({"name": name, "type": match})

    print("\nSTEP 3  RESOLVE  (different names, same thing)")
    canonical = resolve(entities)

    # Validate every relation against the schema rules. LLMs make mistakes; bad facts stay out.
    kept = []
    for r in relations:
        allowed = RULES[r["relation"]]
        actual = (known[r["source"]], known[r["target"]])
        if actual == allowed:
            kept.append(r)
        else:
            print(f"  REJECTED ({r['source']})-[:{r['relation']}]->({r['target']}): "
                  f"{r['relation']} must go {allowed[0]} -> {allowed[1]}, got {actual[0]} -> {actual[1]}")
    relations = kept
    for raw, clean in sorted(canonical.items()):
        if raw != clean:
            print(f"  '{raw}'  ->  '{clean}'")
    print(f"  {len({e['name'] for e in entities})} raw names  ->  {len(set(canonical.values()))} real entities")

    print("\nSTEP 4  LOAD  into the graph database, then ask a multi-hop question")
    conn = load(entities, relations, canonical)
    n = rows(conn.execute("MATCH (n:Entity) RETURN count(n)"))[0][0]
    m = rows(conn.execute("MATCH ()-[r:RELATED]->() RETURN count(r)"))[0][0]
    print(f"  Graph: {n} nodes, {m} relationships")

    # Our vendors (the companies Acme pays). Shortest path from each one to any sanctions list.
    vendors = ["Apex", "Cobalt", "Evergreen"]
    where = " OR ".join(f"v.name STARTS WITH '{v}'" for v in vendors)
    question = f"""MATCH (v:Entity)-[r:RELATED* SHORTEST 1..6]-(s:Entity {{type: 'SanctionsList'}})
                   WHERE {where}
                   RETURN v.name, properties(nodes(r), 'name'), properties(rels(r), 'type'), s.name"""
    print("\n  Q: Which vendors are linked to a sanctions list, and how?")
    answers = rows(conn.execute(question))
    for start, via, rel_types, end in answers:
        path = [start, *via, end]
        print("   " + " -> ".join(f"{path[i]} [{rel_types[i]}]" for i in range(len(rel_types))) + f" -> {end}")
    if not answers:
        print("   No path found. The extraction above missed or got wrong the facts that link the documents,")
        print("   so the graph is incomplete. Better extraction (a stronger model, better prompt) fixes this.")

    # Why STEP 3 matters: load the same facts WITHOUT resolving names and ask again.
    raw = load(entities, relations, {e["name"]: e["name"] for e in entities}, "kg_without_resolution")
    found = rows(raw.execute(question))
    print(f"\n  Same question on a graph built WITHOUT step 3: {len(found)} path(s) found.")
    print("  The names never join up, so the chain is broken. Resolution is what connects the documents.")
