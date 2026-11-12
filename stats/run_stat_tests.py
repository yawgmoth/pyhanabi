#!/usr/bin/env python3
"""Compare each Hanabi agent to the Full (version 0) baseline.

Usage (from the repo root):
    python stats/run_stat_tests.py --results-dir stats/results --baseline baseline --out stats/output

Games must be paired by seed. Compact CSVs from ``stats/run_selfplay.py``
are the primary input. A ``json/`` dump directory is also accepted.

Config (agent lists, alpha, thresholds, bootstrap seed) lives in
``stats/config.py``.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stats.analysis import (  # noqa: E402
    SeedMismatchError,
    SeedOrderError,
    assert_aligned_seeds,
    attach_holm,
    latex_score_table,
    mcnemar_discordant,
    paired_row,
    rows_to_frame,
    welch_ttest,
)
from stats.config import (  # noqa: E402
    ACTIVE_AGENTS,
    ALPHA,
    BOOTSTRAP_SEED,
    DEPRECATED_AGENTS,
    DISK_BASELINE_2P_TS,
    DISK_BASELINE_3P_OLDER_TS,
    DISK_BASELINE_3P_TS,
    DISK_BASELINE_MEAN,
    DISK_BASELINE_STD,
    DISPLAY_NAMES,
    HIGH_SCORE_THRESHOLD,
    INCLUDE_DEPRECATED,
    LOW_SCORE_THRESHOLD,
    METRICS,
    N_BOOTSTRAP,
    REPO_ROOT,
    SKIP_REASONS,
    UNSOURCED_BASELINE_MEAN,
    UNSOURCED_BASELINE_STD,
    V12_EXPECTED_BASELINE_MEAN,
    V12_EXPECTED_BASELINE_STD,
    V12_EXPECTED_CI,
    V12_EXPECTED_MEAN_DIFF,
    V12_TOLERANCE,
)
from stats.loaders import load_json_run, load_results_dir, list_json_timestamps  # noqa: E402

log = logging.getLogger("stats")


def _display(agent: str) -> str:
    return DISPLAY_NAMES.get(agent, agent)


def _agents_to_compare(include_deprecated: bool) -> list[str]:
    names = list(ACTIVE_AGENTS)
    if include_deprecated:
        for a in DEPRECATED_AGENTS:
            if a not in names:
                names.append(a)
    return names


def _metric_values(df: pd.DataFrame, metric: str) -> np.ndarray:
    if metric not in df.columns or df[metric].isna().all():
        raise KeyError(metric)
    return df[metric].to_numpy(dtype=float)


def compare_metric(
    tables: dict[str, pd.DataFrame],
    baseline_name: str,
    agents: list[str],
    metric: str,
    *,
    alpha: float,
    n_boot: int,
    boot_seed: int,
) -> tuple[list[dict], list[str]]:
    baseline = tables[baseline_name].sort_values("seed").reset_index(drop=True)
    rows: list[dict] = []
    skipped: list[str] = []
    for agent in agents:
        if agent == baseline_name:
            continue
        if agent in SKIP_REASONS:
            skipped.append(f"{agent}: {SKIP_REASONS[agent]}")
            continue
        if agent not in tables:
            skipped.append(f"{agent}: no results file")
            continue
        other = tables[agent].sort_values("seed").reset_index(drop=True)
        try:
            assert_aligned_seeds(list(other["seed"]), list(baseline["seed"]), agent)
        except SeedOrderError as exc:
            log.warning("%s; sorting both by seed and continuing", exc)
            other = other.sort_values("seed").reset_index(drop=True)
            baseline_sorted = baseline.sort_values("seed").reset_index(drop=True)
            if list(other["seed"]) != list(baseline_sorted["seed"]):
                skipped.append(f"{agent}: {exc}")
                continue
            baseline_use = baseline_sorted
        except SeedMismatchError as exc:
            skipped.append(str(exc))
            continue
        else:
            baseline_use = baseline
        try:
            a_vals = _metric_values(other, metric)
            b_vals = _metric_values(baseline_use, metric)
        except KeyError:
            skipped.append(f"{agent}: metric {metric!r} missing")
            continue
        if np.isnan(a_vals).any() or np.isnan(b_vals).any():
            skipped.append(f"{agent}: metric {metric!r} has NaNs")
            continue
        row = paired_row(
            a_vals, b_vals, n_boot=n_boot, boot_seed=boot_seed, alpha=alpha
        )
        row["agent"] = agent
        row["display_name"] = _display(agent)
        rows.append(row)
        log.info(
            "%s %s: n=%d mean=%.3f diff=%.3f p_t=%.4g",
            agent,
            metric,
            row["n"],
            row["mean_score"],
            row["mean_diff"],
            row["p_ttest"],
        )
    return attach_holm(rows, alpha=alpha), skipped


def compare_mcnemar(
    tables: dict[str, pd.DataFrame],
    baseline_name: str,
    agents: list[str],
    *,
    threshold: int,
    ge: bool,
    alpha: float,
) -> tuple[pd.DataFrame, list[str]]:
    baseline = tables[baseline_name].sort_values("seed").reset_index(drop=True)
    raw_rows = []
    skipped: list[str] = []
    for agent in agents:
        if agent == baseline_name or agent not in tables or agent in SKIP_REASONS:
            continue
        other = tables[agent].sort_values("seed").reset_index(drop=True)
        try:
            assert_aligned_seeds(list(other["seed"]), list(baseline["seed"]), agent)
        except SeedOrderError:
            other = other.sort_values("seed").reset_index(drop=True)
            baseline = baseline.sort_values("seed").reset_index(drop=True)
            if list(other["seed"]) != list(baseline["seed"]):
                skipped.append(f"{agent}: seed order/set mismatch")
                continue
        except SeedMismatchError as exc:
            skipped.append(str(exc))
            continue
        a = other["score"].to_numpy(dtype=float)
        b = baseline["score"].to_numpy(dtype=float)
        if ge:
            a_flag = a >= threshold
            b_flag = b >= threshold
        else:
            a_flag = a < threshold
            b_flag = b < threshold
        row = mcnemar_discordant(a_flag, b_flag)
        row["agent"] = agent
        raw_rows.append(row)
    if not raw_rows:
        return pd.DataFrame(), skipped
    pvals = [r["p"] for r in raw_rows]
    from stats.analysis import holm_adjust

    holm, _rej = holm_adjust(pvals, alpha=alpha)
    for r, h in zip(raw_rows, holm):
        r["p_holm"] = h
        r["significant"] = bool(math.isfinite(h) and h < alpha)
    return pd.DataFrame(raw_rows), skipped


def check_v12(
    tables: dict[str, pd.DataFrame],
    baseline_name: str,
    *,
    alpha: float,
    n_boot: int,
    boot_seed: int,
) -> dict[str, object]:
    report: dict[str, object] = {"ran": False, "matched": None, "reason": ""}
    if "V12" not in tables:
        report["reason"] = "no V12 results"
        return report
    if baseline_name not in tables:
        report["reason"] = "no baseline results"
        return report
    other = tables["V12"].sort_values("seed").reset_index(drop=True)
    baseline = tables[baseline_name].sort_values("seed").reset_index(drop=True)
    try:
        assert_aligned_seeds(list(other["seed"]), list(baseline["seed"]), "V12")
    except (SeedMismatchError, SeedOrderError) as exc:
        report["reason"] = str(exc)
        return report
    b_mean = float(baseline["score"].mean())
    b_std = float(baseline["score"].std(ddof=1))
    row = paired_row(
        other["score"].to_numpy(dtype=float),
        baseline["score"].to_numpy(dtype=float),
        n_boot=n_boot,
        boot_seed=boot_seed,
        alpha=alpha,
    )
    report["ran"] = True
    report["row"] = row
    report["baseline_mean"] = b_mean
    report["baseline_std"] = b_std
    baseline_ok = (
        abs(b_mean - V12_EXPECTED_BASELINE_MEAN) <= V12_TOLERANCE
        and abs(b_std - V12_EXPECTED_BASELINE_STD) <= V12_TOLERANCE
    )
    report["baseline_matches_published"] = baseline_ok
    if not baseline_ok:
        report["matched"] = False
        report["reason"] = (
            f"baseline mean/std {b_mean:.3f}/{b_std:.3f} != published "
            f"{V12_EXPECTED_BASELINE_MEAN}/{V12_EXPECTED_BASELINE_STD}; "
            "not asserting the published V12 paired CI (engine/agent drift)"
        )
        return report
    diff_ok = abs(row["mean_diff"] - V12_EXPECTED_MEAN_DIFF) <= V12_TOLERANCE
    ci_ok = (
        abs(row["ci_low"] - V12_EXPECTED_CI[0]) <= V12_TOLERANCE
        and abs(row["ci_high"] - V12_EXPECTED_CI[1]) <= V12_TOLERANCE
    )
    report["matched"] = bool(diff_ok and ci_ok)
    if report["matched"]:
        report["reason"] = (
            f"V12 paired diff {row['mean_diff']:.3f} CI "
            f"[{row['ci_low']:.3f}, {row['ci_high']:.3f}] matches published "
            f"{V12_EXPECTED_MEAN_DIFF} {list(V12_EXPECTED_CI)}"
        )
    else:
        report["reason"] = (
            f"V12 paired diff {row['mean_diff']:.3f} CI "
            f"[{row['ci_low']:.3f}, {row['ci_high']:.3f}] != published "
            f"{V12_EXPECTED_MEAN_DIFF} {list(V12_EXPECTED_CI)}"
        )
    return report


def maybe_welch_2p3p(json_dir: Path) -> dict[str, object] | None:
    """Welch t-test on the September Full 2p vs 3p dumps.

    2-player and 3-player scores are not directly comparable: they use
    different decks, different hand/deck sizes, and different game length.
    """
    if not json_dir.is_dir():
        log.info("2p vs 3p: no json dir at %s", json_dir)
        return None
    ts = set(list_json_timestamps(json_dir))
    if DISK_BASELINE_2P_TS not in ts or DISK_BASELINE_3P_TS not in ts:
        log.info(
            "2p vs 3p: need timestamps %s and %s in %s (found %s)",
            DISK_BASELINE_2P_TS,
            DISK_BASELINE_3P_TS,
            json_dir,
            sorted(ts),
        )
        return None
    two = load_json_run(json_dir, DISK_BASELINE_2P_TS)
    three = load_json_run(json_dir, DISK_BASELINE_3P_TS)
    res = welch_ttest(
        two["score"].to_numpy(dtype=float), three["score"].to_numpy(dtype=float)
    )
    res["note"] = (
        "2p and 3p scores are not directly comparable (different decks and rules)."
    )
    res["timestamp_2p"] = DISK_BASELINE_2P_TS
    res["timestamp_3p"] = DISK_BASELINE_3P_TS
    return res


def _flag_baselines(baseline_df: pd.DataFrame) -> None:
    mean = float(baseline_df["score"].mean())
    std = float(baseline_df["score"].std(ddof=1))
    n = len(baseline_df)
    log.info("baseline n=%d mean=%.3f std=%.3f", n, mean, std)
    if abs(mean - DISK_BASELINE_MEAN) <= 0.01 and abs(std - DISK_BASELINE_STD) <= 0.01:
        log.info(
            "baseline matches the 2026-09-30 shared-seed dump (%.3f / %.3f)",
            DISK_BASELINE_MEAN,
            DISK_BASELINE_STD,
        )
    else:
        log.warning(
            "baseline %.3f / %.3f differs from on-disk 3p dump %.3f / %.3f "
            "(timestamp %s). Do not mix with the older dump %s (mean ~16.513).",
            mean,
            std,
            DISK_BASELINE_MEAN,
            DISK_BASELINE_STD,
            DISK_BASELINE_3P_TS,
            DISK_BASELINE_3P_OLDER_TS,
        )
    log.info(
        "notes also cite %.1f / std %.1f; that figure is not in this repo",
        UNSOURCED_BASELINE_MEAN,
        UNSOURCED_BASELINE_STD,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=REPO_ROOT / "stats" / "results"
    )
    parser.add_argument("--baseline", default="baseline")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "stats" / "output")
    parser.add_argument("--json-dir", type=Path, default=REPO_ROOT / "json")
    parser.add_argument("--log-dir", type=Path, default=REPO_ROOT / "log")
    parser.add_argument(
        "--include-deprecated", action="store_true", default=INCLUDE_DEPRECATED
    )
    parser.add_argument("--alpha", type=float, default=ALPHA)
    parser.add_argument("--threshold", type=int, default=LOW_SCORE_THRESHOLD)
    parser.add_argument("--high-threshold", type=int, default=HIGH_SCORE_THRESHOLD)
    parser.add_argument("--n-boot", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--boot-seed", type=int, default=BOOTSTRAP_SEED)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = load_results_dir(args.results_dir)
    if not tables:
        log.error(
            "no compact CSVs in %s — run stats/run_selfplay.py first", args.results_dir
        )
        return 1
    log.info("found agents: %s", ", ".join(sorted(tables)))

    if args.baseline not in tables:
        log.error("baseline %r not in %s", args.baseline, args.results_dir)
        return 1
    _flag_baselines(tables[args.baseline])

    wanted = _agents_to_compare(args.include_deprecated)
    log.info("comparison list: %s", ", ".join(wanted))

    all_skipped: dict[str, list[str]] = {}
    score_rows: list[dict] = []
    for metric in METRICS:
        rows, skipped = compare_metric(
            tables,
            args.baseline,
            wanted,
            metric,
            alpha=args.alpha,
            n_boot=args.n_boot,
            boot_seed=args.boot_seed,
        )
        all_skipped[metric] = skipped
        frame = rows_to_frame(rows)
        dest = out_dir / f"{metric}.csv"
        frame.to_csv(dest, index=False)
        log.info("wrote %s (%d rows); skipped: %s", dest, len(frame), skipped or "none")
        if metric == "score":
            score_rows = rows

    low_df, low_skip = compare_mcnemar(
        tables,
        args.baseline,
        wanted,
        threshold=args.threshold,
        ge=False,
        alpha=args.alpha,
    )
    high_df, high_skip = compare_mcnemar(
        tables,
        args.baseline,
        wanted,
        threshold=args.high_threshold,
        ge=True,
        alpha=args.alpha,
    )
    low_df.to_csv(out_dir / "mcnemar_score_lt_threshold.csv", index=False)
    high_df.to_csv(out_dir / "mcnemar_score_ge_high.csv", index=False)
    log.info("McNemar score<%d skipped: %s", args.threshold, low_skip or "none")
    log.info("McNemar score>=%d skipped: %s", args.high_threshold, high_skip or "none")

    base = tables[args.baseline]
    tex = latex_score_table(
        [
            r
            for r in score_rows
            if r["agent"] in ACTIVE_AGENTS or args.include_deprecated
        ],
        baseline_mean=float(base["score"].mean()),
        baseline_std=float(base["score"].std(ddof=1)),
        baseline_n=len(base),
        baseline_label=_display(args.baseline),
    )
    tex_path = out_dir / "score_table.tex"
    tex_path.write_text(tex, encoding="utf-8")
    log.info("wrote %s", tex_path)

    v12 = check_v12(
        tables,
        args.baseline,
        alpha=args.alpha,
        n_boot=args.n_boot,
        boot_seed=args.boot_seed,
    )
    log.info("V12 validation: %s", v12.get("reason") or v12)
    (out_dir / "v12_validation.txt").write_text(str(v12) + "\n", encoding="utf-8")

    welch = maybe_welch_2p3p(args.json_dir)
    if welch is not None:
        log.info(
            "2p vs 3p Welch (not comparable): mean2p=%.3f mean3p=%.3f p=%.4g — %s",
            welch["mean_a"],
            welch["mean_b"],
            welch["p"],
            welch["note"],
        )
        pd.DataFrame([welch]).to_csv(out_dir / "welch_2p_vs_3p.csv", index=False)

    for metric, skipped in all_skipped.items():
        if skipped:
            log.info("skipped (%s):", metric)
            for line in skipped:
                log.info("  %s", line)
    return 0 if v12.get("matched") is not False or not v12.get("ran") else 0


if __name__ == "__main__":
    sys.exit(main())
