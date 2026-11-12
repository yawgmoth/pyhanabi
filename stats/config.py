"""Shared configuration for self-play and statistical tests.

Assumptions
-----------
- Games are paired by deck seed. ``hana_sim.set_deck_seed(s)`` and
  ``random.seed(s)`` with ``s = 1..N`` identify a unique deck.
- Lives lost per game is ``INITIAL_LIVES - lives_remaining`` (Hanabi starts
  with 3 lives; each misplay / failed play costs one).
- Critical discards are summed over all players in a game.
- Only agent-vs-baseline tests are run (no within-track pairwise tests).
- V6 with a ``hints > 3`` threshold is not implemented in this codebase;
  V6 uses ``hints > 0``. That row is skipped.
- Two baseline figures appear in notes (16.6 / std 2.1, and 16.584 / std
  1.84). The on-disk shared-seed dump is 16.584 / 1.836 (3p 2026-09-30).
  16.6 / 2.1 is not in this repo.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALPHA = 0.05
LOW_SCORE_THRESHOLD = 10
HIGH_SCORE_THRESHOLD = 24
N_GAMES = 1000
N_PLAYERS = 3
INITIAL_LIVES = 3
N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 0
V12_ETA = 0.9
V12_LAMBDA = 0.5

# Published V12 sanity-check (N=1000, eta=0.90, lambda=0.50) vs the
# 2026-09-30 baseline dump.
V12_EXPECTED_BASELINE_MEAN = 16.584
V12_EXPECTED_BASELINE_STD = 1.836
V12_EXPECTED_MEAN_DIFF = -0.200
V12_EXPECTED_CI = (-0.311, -0.089)
V12_TOLERANCE = 0.01

# On-disk September Full-agent dumps (game number == seed).
DISK_BASELINE_3P_TS = "20260930_181448"
DISK_BASELINE_3P_TS_DUP = "20260930_181054"
DISK_BASELINE_3P_OLDER_TS = "20260915_162007"
DISK_BASELINE_2P_TS = "20260916_154859"
DISK_BASELINE_MEAN = 16.584
DISK_BASELINE_STD = 1.836
UNSOURCED_BASELINE_MEAN = 16.6
UNSOURCED_BASELINE_STD = 2.1

PLAYER_NAMES = ("A", "B", "C")

# Integer versions implemented on SelfIntentionalPlayer after hanabilive_converter.
INTEGER_VERSIONS = frozenset(
    {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 17, 18, 19}
)

# Default paper table. V6_hgt3 is listed so it appears in skip logs.
ACTIVE_AGENTS = [
    "V6",
    "V6_hgt3",
    "V8",
    "V9",
    "V10",
    "V11",
    "V14",
    "V15",
    "V16",
    "V17",
    "V18",
    "V19",
    "case",
]

DEPRECATED_AGENTS = [
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V7",
    "V12",
    "V13",
]

INCLUDE_DEPRECATED = False

# Always generated / compared, even when deprecated are off.
REQUIRED_AGENTS = ["baseline", "V12"]

SKIP_REASONS = {
    "V6_hgt3": (
        "V6 h>3 is not implemented; give_intentional_hint_v6 uses hints > 0. "
        "Closest relative is V19_CRIT_HINT_MIN_TOKENS = 4."
    ),
}

DISPLAY_NAMES = {
    "baseline": "Baseline (Full v0)",
    "V6": "V6 (h>0)",
    "V6_hgt3": "V6 (h>3)",
    "V12": "V12 ($\\eta{=}0.90$, $\\lambda{=}0.50$)",
    "case": "Case-based",
}

CSV_COLUMNS = [
    "agent",
    "n",
    "mean_score",
    "std",
    "mean_diff",
    "ci_low",
    "ci_high",
    "boot_ci_low",
    "boot_ci_high",
    "cohens_d",
    "p_ttest",
    "p_ttest_holm",
    "p_wilcoxon",
    "p_wilcoxon_holm",
    "significant",
    "tests_agree",
]

METRICS = ("score", "lives_lost", "critical_discards")
