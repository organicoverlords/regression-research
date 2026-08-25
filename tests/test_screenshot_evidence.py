from __future__ import annotations

import json
from pathlib import Path

from tools.screenshot_evidence import DEFAULT_INDEX, load_index, search


def test_index_is_valid_and_rated() -> None:
    data = load_index()
    assert data["schema_version"] == "1.0.0"
    assert data["cases"]
    assert all(1 <= int(case["rating"]) <= 5 for case in data["cases"])
    assert all(case.get("observation") for case in data["cases"])


def test_search_finds_positive_and_negative_controls() -> None:
    good = search("correct_and_continue", min_rating=5)
    bad = search("plan_loop", min_rating=5)
    assert [case["id"] for case in good] == ["regression-worker-mcp-parameter-recovery"]
    assert [case["id"] for case in bad] == ["bad-cold-baseline-next-step-loop"]


def test_search_supports_filename_and_phenotype() -> None:
    by_file = search("96558d60-d563-4be8-8fcb-04a5c69a9741.png")
    by_kind = search("delivery_acceptance_condition_drop")
    assert by_file[0]["id"] == "p3-456-persistent-runtime-proof"
    assert by_kind[0]["id"] == "image-delivery-context-failure"
