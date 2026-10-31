"""Unit tests for recreate engine."""

from src.recreate import (
    compute_script_similarity,
    extract_ngrams,
    select_reference_and_variant,
)


def test_extract_ngrams():
    text = "Nikola Tesla woke up in Silicon Valley"
    ngrams = extract_ngrams(text, n=3)
    assert len(ngrams) == 5
    assert ("nikola", "tesla", "woke") in ngrams


def test_compute_script_similarity_different():
    script1 = "Julius Caesar marveled at modern electric supercars and neural interfaces."
    script2 = "Hey yo nicer than anybody you say the nicest thirty years."
    sim = compute_script_similarity(script1, script2)
    assert sim == 0.0


def test_compute_script_similarity_identical():
    script1 = "This is a full sentence containing repeated words for testing similarity."
    script2 = "This is a full sentence containing repeated words for testing similarity."
    sim = compute_script_similarity(script1, script2)
    assert sim == 1.0


def test_select_reference_and_variant():
    sel = select_reference_and_variant()
    assert "reference_file" in sel
    assert "style_variant" in sel
    assert "topic_angle" in sel
    assert sel["reference_file"].endswith((".mp4", ".mov", ".webm"))
