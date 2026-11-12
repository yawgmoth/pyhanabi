"""Paired statistical tests. No game-engine imports (safe for unit tests)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

from stats.config import (
    ALPHA,
    BOOTSTRAP_SEED,
    CSV_COLUMNS,
    N_BOOTSTRAP,
)


def _as_1d(x: np.ndarray | list[float]) -> np.ndarray:
    arr = np.asarray(x, dtype=float).ravel()
    if arr.ndim != 1:
        raise ValueError(f"expected a 1-d array, got shape {arr.shape}")
    return arr


def assert_aligned_seeds(
    agent_seeds: list[int], baseline_seeds: list[int], agent: str
) -> None:
    """Require identical seed sets. Prefer identical order; sort if only order differs."""
    if list(agent_seeds) == list(baseline_seeds):
        return
    if set(agent_seeds) == set(baseline_seeds) and len(agent_seeds) == len(
        baseline_seeds
    ):
        raise SeedOrderError(
            f"{agent}: seed sets match but order differs "
            f"(agent {agent_seeds[:5]}... vs baseline {baseline_seeds[:5]}...)"
        )
    missing_a = sorted(set(baseline_seeds) - set(agent_seeds))
    missing_b = sorted(set(agent_seeds) - set(baseline_seeds))
    raise SeedMismatchError(
        f"{agent}: seed sets differ. "
        f"missing_from_agent={missing_a[:10]} missing_from_baseline={missing_b[:10]}"
    )


class SeedMismatchError(ValueError):
    pass


class SeedOrderError(ValueError):
    pass


def paired_mean_ci(
    diffs: np.ndarray, alpha: float = ALPHA
) -> tuple[float, float, float, float]:
    """Return mean, sample std, t-based CI low, CI high of `diffs`."""
    d = _as_1d(diffs)
    n = len(d)
    mean = float(np.mean(d))
    if n < 2:
        return mean, float("nan"), float("nan"), float("nan")
    std = float(np.std(d, ddof=1))
    se = std / math.sqrt(n)
    t_crit = float(stats.t.ppf(1 - alpha / 2, n - 1))
    return mean, std, mean - t_crit * se, mean + t_crit * se


def bootstrap_mean_ci(
    diffs: np.ndarray,
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = ALPHA,
) -> tuple[float, float]:
    """Percentile CI of the mean by resampling seeds with replacement."""
    d = _as_1d(diffs)
    n = len(d)
    if n == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = d[idx].mean(axis=1)
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return lo, hi


def cohens_d_paired(diffs: np.ndarray) -> float:
    d = _as_1d(diffs)
    if len(d) < 2:
        return float("nan")
    std = float(np.std(d, ddof=1))
    mean = float(np.mean(d))
    if std == 0.0:
        return 0.0 if mean == 0.0 else float("inf")
    return mean / std


def paired_pvalues(agent: np.ndarray, baseline: np.ndarray) -> tuple[float, float]:
    """Paired t-test and Wilcoxon signed-rank p-values on agent vs baseline.

    All-zero differences: both p-values are 1.0 (no crash).
    """
    a = _as_1d(agent)
    b = _as_1d(baseline)
    if len(a) != len(b):
        raise ValueError(f"length mismatch: agent {len(a)} vs baseline {len(b)}")
    diffs = a - b
    if len(diffs) == 0:
        return float("nan"), float("nan")
    if np.allclose(diffs, 0.0):
        return 1.0, 1.0
    if len(diffs) > 1 and float(np.std(diffs, ddof=1)) == 0.0:
        p_t = 0.0
    else:
        t_res = stats.ttest_rel(a, b)
        p_t = float(t_res.pvalue)
        if not math.isfinite(p_t):
            p_t = 1.0
    try:
        w_res = stats.wilcoxon(diffs, zero_method="wilcox", alternative="two-sided")
        p_w = float(w_res.pvalue)
        if not math.isfinite(p_w):
            p_w = 1.0
    except ValueError:
        p_w = 1.0
    return p_t, p_w


def holm_adjust(
    pvalues: list[float], alpha: float = ALPHA
) -> tuple[list[float], list[bool]]:
    """Holm family-wise adjustment. NaNs are left as NaN and treated as not significant."""
    if not pvalues:
        return [], []
    finite_idx = [
        i for i, p in enumerate(pvalues) if p is not None and math.isfinite(p)
    ]
    adjusted = [float("nan")] * len(pvalues)
    reject = [False] * len(pvalues)
    if not finite_idx:
        return adjusted, reject
    raw = [pvalues[i] for i in finite_idx]
    rej, holm, _, _ = multipletests(raw, alpha=alpha, method="holm")
    for i, r, h in zip(finite_idx, rej, holm):
        adjusted[i] = float(h)
        reject[i] = bool(r)
    return adjusted, reject


def paired_row(
    agent_vals: np.ndarray,
    baseline_vals: np.ndarray,
    *,
    n_boot: int = N_BOOTSTRAP,
    boot_seed: int = BOOTSTRAP_SEED,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    """Unadjusted paired comparison of one agent vs baseline on one metric."""
    a = _as_1d(agent_vals)
    b = _as_1d(baseline_vals)
    diffs = a - b
    mean_diff, _std_d, ci_lo, ci_hi = paired_mean_ci(diffs, alpha=alpha)
    boot_lo, boot_hi = bootstrap_mean_ci(
        diffs, n_boot=n_boot, seed=boot_seed, alpha=alpha
    )
    p_t, p_w = paired_pvalues(a, b)
    n = len(a)
    mean = float(np.mean(a)) if n else float("nan")
    std = float(np.std(a, ddof=1)) if n > 1 else float("nan")
    return {
        "n": n,
        "mean_score": mean,
        "std": std,
        "mean_diff": mean_diff,
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "boot_ci_low": boot_lo,
        "boot_ci_high": boot_hi,
        "cohens_d": cohens_d_paired(diffs),
        "p_ttest": p_t,
        "p_wilcoxon": p_w,
    }


def attach_holm(
    rows: list[dict[str, Any]], alpha: float = ALPHA
) -> list[dict[str, Any]]:
    """Add Holm-adjusted p-values, significant flag, and tests_agree to each row."""
    p_t = [r["p_ttest"] for r in rows]
    p_w = [r["p_wilcoxon"] for r in rows]
    holm_t, rej_t = holm_adjust(p_t, alpha=alpha)
    holm_w, rej_w = holm_adjust(p_w, alpha=alpha)
    out = []
    for r, ht, hw, st, sw in zip(rows, holm_t, holm_w, rej_t, rej_w):
        item = dict(r)
        item["p_ttest_holm"] = ht
        item["p_wilcoxon_holm"] = hw
        item["significant"] = bool(st)
        item["tests_agree"] = bool(st) == bool(sw)
        out.append(item)
    return out


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=CSV_COLUMNS)
    df = pd.DataFrame(rows)
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[CSV_COLUMNS]


def mcnemar_discordant(
    agent_flag: np.ndarray, baseline_flag: np.ndarray
) -> dict[str, Any]:
    """McNemar exact test on paired binary outcomes.

    Cells are:
      n11 = both True, n00 = both False,
      n10 = agent True / baseline False,
      n01 = agent False / baseline True.
    """
    a = np.asarray(agent_flag, dtype=bool).ravel()
    b = np.asarray(baseline_flag, dtype=bool).ravel()
    if len(a) != len(b):
        raise ValueError("paired flags must have the same length")
    n11 = int(np.sum(a & b))
    n00 = int(np.sum(~a & ~b))
    n10 = int(np.sum(a & ~b))
    n01 = int(np.sum(~a & b))
    table = np.array([[n00, n01], [n10, n11]], dtype=int)
    # exact=True uses the binomial test on discordant pairs.
    try:
        res = mcnemar(table, exact=True)
        p = float(res.pvalue)
    except (ValueError, ZeroDivisionError):
        p = 1.0
    if not math.isfinite(p):
        p = 1.0
    return {
        "n": len(a),
        "n00": n00,
        "n01": n01,
        "n10": n10,
        "n11": n11,
        "p": p,
    }


def welch_ttest(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    """Independent two-sample Welch t-test (unequal variances)."""
    x = _as_1d(a)
    y = _as_1d(b)
    res = stats.ttest_ind(x, y, equal_var=False)
    return {
        "n_a": len(x),
        "n_b": len(y),
        "mean_a": float(np.mean(x)) if len(x) else float("nan"),
        "mean_b": float(np.mean(y)) if len(y) else float("nan"),
        "std_a": float(np.std(x, ddof=1)) if len(x) > 1 else float("nan"),
        "std_b": float(np.std(y, ddof=1)) if len(y) > 1 else float("nan"),
        "p": float(res.pvalue),
        "statistic": float(res.statistic),
    }


def fmt_p(p: float) -> str:
    if p is None or not math.isfinite(p):
        return "---"
    if p < 0.001:
        return "$<0.001$"
    return f"{p:.3f}"


def fmt_num(x: float, digits: int = 3) -> str:
    if x is None or not math.isfinite(x):
        return "---"
    return f"{x:.{digits}f}"


def latex_score_table(
    rows: list[dict[str, Any]],
    *,
    baseline_mean: float,
    baseline_std: float,
    baseline_n: int,
    baseline_label: str = "Baseline (Full v0)",
) -> str:
    """Booktabs table: Agent | Mean | Diff vs. baseline | 95% CI | Holm-adjusted p."""
    lines = [
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Agent & Mean & Diff vs.\ baseline & 95\% CI & Holm-adjusted $p$ \\",
        r"\midrule",
    ]
    base_mean_s = fmt_num(baseline_mean, 3)
    lines.append(
        f"{baseline_label} & {base_mean_s} "
        f"(std {fmt_num(baseline_std, 3)}, $n$={baseline_n}) & --- & --- & --- \\\\"
    )
    for r in rows:
        name = r.get("display_name", r["agent"])
        mean_s = fmt_num(r["mean_score"], 3)
        diff_s = fmt_num(r["mean_diff"], 3)
        ci_s = f"[{fmt_num(r['ci_low'], 3)}, {fmt_num(r['ci_high'], 3)}]"
        p_s = fmt_p(r["p_ttest_holm"])
        cells = [name, mean_s, diff_s, ci_s, p_s]
        if r.get("significant"):
            cells = [f"\\textbf{{{c}}}" for c in cells]
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(lines)
