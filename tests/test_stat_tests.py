"""Synthetic tests for the paired-stats pipeline. No game engine required."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stats.analysis import (
    SeedMismatchError,
    SeedOrderError,
    assert_aligned_seeds,
    attach_holm,
    holm_adjust,
    mcnemar_discordant,
    paired_pvalues,
    paired_row,
)
from stats.loaders import _standardize
import pandas as pd


def test_identical_agents_zero_diff_and_p_one():
    x = np.array([10.0, 12.0, 15.0, 16.0, 18.0])
    row = paired_row(x, x.copy())
    assert row["mean_diff"] == pytest.approx(0.0)
    assert row["p_ttest"] == pytest.approx(1.0)
    assert row["p_wilcoxon"] == pytest.approx(1.0)
    assert row["cohens_d"] == pytest.approx(0.0)


def test_constant_plus_one_shift():
    baseline = np.array([8.0, 9.0, 10.0, 11.0, 12.0, 14.0, 16.0, 20.0])
    agent = baseline + 1.0
    row = paired_row(agent, baseline)
    assert row["mean_diff"] == pytest.approx(1.0)
    assert row["mean_score"] == pytest.approx(float(np.mean(agent)))
    p_t, p_w = paired_pvalues(agent, baseline)
    assert p_t < 0.05
    assert p_w < 0.05


def test_holm_adjusted_p_at_least_raw():
    raw = [0.001, 0.04, 0.20, 0.80]
    adjusted, _ = holm_adjust(raw, alpha=0.05)
    for p, h in zip(raw, adjusted):
        assert h >= p - 1e-15


def test_holm_on_paired_rows():
    x = np.arange(20.0)
    rows = [
        {"agent": "same", **paired_row(x, x.copy())},
        {"agent": "plus1", **paired_row(x + 1.0, x)},
    ]
    out = attach_holm(rows, alpha=0.05)
    for r in out:
        assert r["p_ttest_holm"] >= r["p_ttest"] - 1e-15
        assert r["p_wilcoxon_holm"] >= r["p_wilcoxon"] - 1e-15
    assert out[0]["significant"] is False
    assert out[1]["significant"] is True
    assert out[1]["tests_agree"] is True


def test_seed_sets_must_match():
    with pytest.raises(SeedMismatchError):
        assert_aligned_seeds([1, 2, 3], [1, 2, 4], "V8")


def test_seed_order_mismatch():
    with pytest.raises(SeedOrderError):
        assert_aligned_seeds([1, 3, 2], [1, 2, 3], "V8")


def test_identical_seed_order_ok():
    assert_aligned_seeds([1, 2, 3], [1, 2, 3], "V8")


def test_standardize_sorts_and_derives_lives_lost():
    df = pd.DataFrame(
        {"seed": [3, 1, 2], "score": [10, 11, 12], "lives_remaining": [3, 2, 0]}
    )
    out = _standardize(df, "V8")
    assert list(out["seed"]) == [1, 2, 3]
    assert list(out["lives_lost"]) == [1.0, 3.0, 0.0]


def test_mcnemar_symmetric_is_one():
    a = np.array([True, True, False, False])
    b = np.array([True, True, False, False])
    row = mcnemar_discordant(a, b)
    assert row["n10"] == 0
    assert row["n01"] == 0
    assert row["p"] == pytest.approx(1.0)


def test_mcnemar_discordant_counts():
    # agent low on 2 extra decks; baseline low on 0 extra
    agent = np.array([True, True, False, False, True])
    base = np.array([True, False, False, False, False])
    row = mcnemar_discordant(agent, base)
    assert row["n11"] == 1
    assert row["n10"] == 2
    assert row["n01"] == 0
    assert row["p"] < 1.0


def test_all_zero_wilcoxon_does_not_raise():
    p_t, p_w = paired_pvalues(np.zeros(8), np.zeros(8))
    assert p_t == 1.0
    assert p_w == 1.0
    assert math.isfinite(p_t)
