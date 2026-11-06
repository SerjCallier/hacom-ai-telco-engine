"""Retrieval quality is asserted, not claimed.

Each case pairs an operator phrasing (Spanish or English) with the runbook section a
network engineer should be shown. This is a small eval set by design: it pins the
behaviour that matters and fails loudly when a corpus edit breaks routing.
"""

from __future__ import annotations

import pytest

from app.rag.corpus import load_corpus
from app.rag.index import Bm25Retriever, get_retriever, tokenize

# (query, expected chunk id)
EVAL_SET: list[tuple[str, str]] = [
    # Congestion: the detection section is where the utilisation/throughput pair is defined.
    ("PRB alto pero el throughput está bajo, qué es", "radio-resource-congestion#detection"),
    ("usa mucha capacidad de radio, hay congestión", "radio-resource-congestion#detection"),
    (
        "usuarios reportan datos lentos en hora pico pero la celda sigue accesible",
        "radio-resource-congestion#symptom",
    ),
    # Coverage vs interference: one classifier section, two opposite remediation branches.
    ("RSRP débil y SINR negativo, qué reviso", "coverage-and-interference#detection"),
    (
        "usuarios con RSRP bueno pero SINR malo, pilot pollution",
        "coverage-and-interference#interference-limited-branch",
    ),
    (
        "antena con tilt mal, usuarios en el borde sin cobertura",
        "coverage-and-interference#coverage-limited-branch",
    ),
    # Drops: the release cause breakdown decides whether radio work is even justified.
    ("drop call rate alto por handover", "drop-call-analysis#release-cause-classification"),
    # Transport: the spectral efficiency check lives in detection.
    ("backhaul saturado y velocidad baja", "transport-and-scheduler#detection"),
]


@pytest.fixture(scope="module")
def retriever() -> Bm25Retriever:
    return Bm25Retriever(load_corpus())


def test_corpus_loads_every_runbook_section() -> None:
    chunks = load_corpus()

    assert len(chunks) >= 18
    assert all(chunk.chunk_id for chunk in chunks)
    assert all(chunk.source for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


@pytest.mark.parametrize(("query", "expected"), EVAL_SET)
def test_expected_section_is_retrieved(retriever: Bm25Retriever, query: str, expected: str) -> None:
    hits = retriever.search(query, limit=3)

    assert [hit.chunk.chunk_id for hit in hits], f"no retrieval for {query!r}"
    assert expected in [hit.chunk.chunk_id for hit in hits], (
        f"{expected} not in top 3 for {query!r}: {[hit.chunk.chunk_id for hit in hits]}"
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("PRB alto y throughput bajo, hay congestión", "radio-resource-congestion#detection"),
        ("backhaul saturado y velocidad baja", "transport-and-scheduler#detection"),
        (
            "usuarios reportan datos lentos en hora pico pero la celda sigue accesible",
            "radio-resource-congestion#symptom",
        ),
    ],
)
def test_clear_cases_hit_top_one(retriever: Bm25Retriever, query: str, expected: str) -> None:
    hits = retriever.search(query, limit=1)

    assert hits and hits[0].chunk.chunk_id == expected


def test_function_words_do_not_outrank_content_terms(retriever: Bm25Retriever) -> None:
    """Regression: a filler word in exactly one document used to win the ranking.

    "about" appeared in a single chunk, so BM25 gave it a large inverse document
    frequency and it beat "congestion", the only content term in the query. The
    stopword list is what prevents that class of failure.
    """
    hits = retriever.search("What does the runbook say about congestion?", limit=3)

    assert hits
    assert all(hit.chunk.doc_id == "radio-resource-congestion" for hit in hits)


def test_scores_are_ordered_and_positive(retriever: Bm25Retriever) -> None:
    hits = retriever.search("congestion throughput", limit=5)

    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(score > 0 for score in scores)


def test_empty_query_returns_nothing(retriever: Bm25Retriever) -> None:
    assert retriever.search("   ", limit=3) == []


def test_stopwords_only_query_returns_nothing(retriever: Bm25Retriever) -> None:
    assert retriever.search("de la que y el", limit=3) == []


def test_spanish_terms_are_normalised_to_the_english_corpus() -> None:
    assert tokenize("congestión") == ["congestion"]
    assert tokenize("Cobertura") == ["coverage"]
    assert tokenize("caídas de llamadas") == ["drop", "call"]
    assert tokenize("backhaul saturado") == ["transport", "saturation"]


def test_saturation_and_congestion_stay_distinct() -> None:
    """A saturated link is not a congested radio interface; the fixes differ."""
    assert tokenize("saturación") == ["saturation"]
    assert tokenize("congestión") == ["congestion"]


def test_default_retriever_is_cached() -> None:
    assert get_retriever() is get_retriever()
