"""Baseline: vector-only RAG.

Documents are split into small chunks, embedded (TF-IDF here so it runs offline;
swap in sentence-transformers / OpenAI / Voyage embeddings and the failure mode
is the same), and the top-k most similar chunks become the LLM's context.

To keep the comparison fair, the "reasoning" step applied to the retrieved
chunks is exactly the same reasoner GraphRAG uses - it just only gets to see
the facts that are inside the top-k chunks. That isolates the real problem:
the *retrieval* never brings back the connecting facts.
"""
import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from kg import build_graph, split_sentences
from reasoner import answer


def _stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokenize(text):
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in ENGLISH_STOP_WORDS]


class VectorRAG:
    def __init__(self, documents, extractor, chunk_sentences=2, top_k=3):
        self.extractor = extractor
        self.top_k = top_k
        self.chunks = []
        for d in documents:
            sents = split_sentences(d["text"])
            for i in range(0, len(sents), chunk_sentences):
                self.chunks.append({
                    "chunk_id": f"{d['id']}#{i // chunk_sentences + 1}",
                    "doc_id": d["id"],
                    "title": d["title"],
                    "text": " ".join(sents[i:i + chunk_sentences]),
                })
        self.vectorizer = TfidfVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None)
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.chunks])

    def retrieve(self, question, k=None):
        sims = cosine_similarity(self.vectorizer.transform([question]), self.matrix)[0]
        order = sims.argsort()[::-1][: k or self.top_k]
        return [dict(self.chunks[i], score=round(float(sims[i]), 3)) for i in order if sims[i] > 0]

    def ask(self, question):
        chunks = self.retrieve(question)
        facts = []
        for c in chunks:
            facts.extend(self.extractor.extract(c["doc_id"], c["text"]))
        context_graph = build_graph(facts, self.extractor)
        result = answer(question, context_graph, self.extractor.ontology)
        result["chunks"] = chunks
        result["context"] = [c["text"] for c in chunks]
        return result
