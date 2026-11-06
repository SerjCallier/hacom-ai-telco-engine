"""Lexical retrieval (BM25) over the runbook corpus.

Why BM25 instead of a vector store for the default path:

* it is deterministic, so retrieval quality can be asserted in tests;
* it needs no model, no network and no index file on disk;
* RAN terminology is dense and specific, which is exactly where lexical
  matching is strongest.

The retriever is exposed behind a small interface so an embedding backend can be
swapped in without touching the agent layer. See ``EmbeddingRetriever`` for the
extension point; it is intentionally not implemented yet rather than faked.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.rag.corpus import Chunk, load_corpus

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Queries arrive in Spanish as often as in English while the corpus is written in
# English. Normalising both sides to one canonical term keeps retrieval honest
# without translating the documents.
SYNONYMS: dict[str, str] = {
    "congestion": "congestion",
    "congestionamiento": "congestion",
    # "Saturacion" is not a synonym of congestion here. Spanish distinguishes a
    # saturated link from a congested radio interface, and so does the corpus
    # ("backhaul saturation" vs "radio resource congestion").
    "saturacion": "saturation",
    "saturado": "saturation",
    "saturada": "saturation",
    "cobertura": "coverage",
    "interferencia": "interference",
    "interference": "interference",
    "caidas": "drop",
    "caida": "drop",
    "llamadas": "call",
    "llamada": "call",
    "handover": "handover",
    "traspaso": "handover",
    "throughput": "throughput",
    "rendimiento": "throughput",
    "velocidad": "throughput",
    "capacidad": "capacity",
    "portadora": "carrier",
    "antena": "antenna",
    "inclinacion": "tilt",
    "senal": "signal",
    "ruido": "noise",
    "transporte": "transport",
    "backhaul": "transport",
    "planificador": "scheduler",
    "scheduler": "scheduler",
    # Entity and symptom vocabulary. The corpus is written in English because the
    # underlying standards are, while operators ask in Spanish; without these the
    # query tokenises to terms that exist in no document and retrieval returns an
    # empty list, which is worse than a weak ranking.
    "usuario": "user",
    "usuarios": "user",
    "celda": "cell",
    "celdas": "cell",
    "celula": "cell",
    "sector": "sector",
    "sectores": "sector",
    "sitio": "site",
    "datos": "data",
    "lento": "slow",
    "lenta": "slow",
    "lentos": "slow",
    "lentas": "slow",
    "pico": "busy",
    "hora": "hour",
    "accesible": "accessible",
    "reportan": "report",
    "reporta": "report",
    "debil": "weak",
    "debiles": "weak",
    "negativo": "negative",
    "negativa": "negative",
    "bueno": "good",
    "buena": "good",
    "malo": "poor",
    "mala": "poor",
    "alto": "high",
    "alta": "high",
    "bajo": "low",
    "baja": "low",
    "borde": "edge",
    "vecino": "neighbour",
    "vecinos": "neighbour",
    "causa": "cause",
    "causas": "cause",
    "reviso": "check",
    "revisar": "check",
    "solucion": "fix",
    "falla": "failure",
    "fallas": "failure",
}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


# A hand-curated list is a known weakness of lexical retrieval: it is always
# incomplete in some language. It is still the right trade here, because the
# failure it prevents is severe. A filler word that happens to appear in exactly
# one document gets a huge IDF weight and outranks the query's real subject. The
# terms below are grouped by language so the list stays maintainable, and
# ``test_function_words_do_not_outrank_content_terms`` pins the behaviour.
STOPWORDS: frozenset[str] = frozenset(
    {
        # Spanish function words
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "que",
        "y",
        "o",
        "en",
        "por",
        "con",
        "para",
        "es",
        "al",
        "se",
        "su",
        "lo",
        "como",
        "mas",
        "muy",
        "si",
        "no",
        "mi",
        "tu",
        "sus",
        "les",
        "hay",
        "esta",
        "este",
        "esto",
        "estos",
        "estas",
        "son",
        "ser",
        "fue",
        "pero",
        "sino",
        "cuando",
        "donde",
        "porque",
        "sobre",
        "entre",
        "hasta",
        "desde",
        "tambien",
        "solo",
        "todo",
        "toda",
        "todos",
        "todas",
        "otro",
        "otra",
        "cual",
        "cuales",
        "quien",
        "quienes",
        "cuanto",
        "cuanta",
        # English function words
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "in",
        "on",
        "for",
        "is",
        "to",
        "with",
        "what",
        "does",
        "do",
        "this",
        "that",
        "it",
        "be",
        "are",
        "was",
        "were",
        "been",
        "has",
        "have",
        "had",
        "its",
        "their",
        "there",
        "then",
        "than",
        "them",
        "these",
        "those",
        "from",
        "at",
        "by",
        "as",
        "if",
        "not",
        "can",
        "could",
        "should",
        "would",
        "will",
        "may",
        "might",
        "must",
        "about",
        "say",
        "says",
        "said",
        "tell",
        "tells",
        "mean",
        "means",
        "when",
        "where",
        "which",
        "who",
        "how",
        "why",
        "also",
        "just",
        "only",
        "any",
        "all",
        "some",
        "more",
        "most",
        "other",
        "such",
        "into",
        "over",
        "under",
        "out",
        "up",
        "down",
        "so",
        "but",
        "because",
        "while",
        "after",
        "before",
        "between",
        "during",
        "without",
        "within",
        "again",
        "here",
        "both",
        "each",
        "few",
        "own",
        "same",
        "too",
        "very",
        "look",
        "looks",
        "looked",
        "nothing",
        "something",
        "anything",
        "please",
    }
)


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(_fold(text))
    return [SYNONYMS.get(token, token) for token in tokens if token not in STOPWORDS]


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class Retriever(Protocol):
    def search(self, query: str, limit: int = 3) -> list[ScoredChunk]: ...


class Bm25Retriever:
    """Okapi BM25 with the usual defaults (k1=1.5, b=0.75)."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        # Section headings carry the author's own summary of the block, so they are
        # weighted above body text. Without this, a short "Verification" paragraph
        # that repeats the vocabulary outranks the section that actually defines it.
        self._docs = [
            tokenize(c.doc_title) + tokenize(c.section) * 3 + tokenize(c.text) for c in chunks
        ]
        self._lengths = [len(d) for d in self._docs]
        self._avg_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        self._idf = self._compute_idf()

    def _compute_idf(self) -> dict[str, float]:
        n = len(self._docs)
        df: dict[str, int] = {}
        for doc in self._docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        return {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def _score(self, query_terms: list[str], index: int) -> float:
        doc = self._docs[index]
        length = self._lengths[index] or 1
        score = 0.0
        for term in query_terms:
            idf = self._idf.get(term)
            if idf is None:
                continue
            tf = doc.count(term)
            if tf == 0:
                continue
            denominator = tf + self._k1 * (1 - self._b + self._b * length / self._avg_length)
            score += idf * (tf * (self._k1 + 1)) / denominator
        return score

    def search(self, query: str, limit: int = 3) -> list[ScoredChunk]:
        terms = tokenize(query)
        if not terms:
            return []
        scored = [
            ScoredChunk(chunk=chunk, score=round(self._score(terms, i), 4))
            for i, chunk in enumerate(self._chunks)
        ]
        scored = [s for s in scored if s.score > 0]
        scored.sort(key=lambda s: (-s.score, s.chunk.chunk_id))
        return scored[:limit]


class EmbeddingRetriever:
    """Extension point for a vector backend (pgvector, Chroma, FAISS...).

    Deliberately unimplemented: a ``NotImplementedError`` is more honest than a
    vector store that pretends to be wired while running keyword matching
    underneath.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "Embedding retrieval is a documented extension point, not a shipped feature."
        )


_default_retriever: Bm25Retriever | None = None


def get_retriever() -> Bm25Retriever:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = Bm25Retriever(load_corpus())
    return _default_retriever
