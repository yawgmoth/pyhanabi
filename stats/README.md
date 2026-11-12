# Statistical tests for 3-player Hanabi self-play

Each agent is compared only to the Full intentional baseline
(version 0), never to other versions. Games are paired by deck seed.

## Pairing assumption

Self-play uses `hana_sim.set_deck_seed(seed)` and `random.seed(seed)`
with `seed = 1..N`. Game `k` of every agent is the same shuffled deck.
That is why we use paired tests rather than independent two-sample
tests. If two CSVs do not share the same seed set, that agent is
skipped.

`N = 1000` unless you pass `--n`.

## Tests and why

- Paired t-test (`scipy.stats.ttest_rel`) on per-seed differences
  `d = agent - baseline`. The mean difference and a t-based 95% CI
  are the primary report.
- Holm adjustment (`statsmodels` `method="holm"`) within each metric.
  Holm is uniformly at least as powerful as Bonferroni. Tukey HSD is
  not used: it assumes independent groups, and these scores are paired
  on fixed decks.
- Wilcoxon signed-rank test as a robustness check (no normality
  assumption). All-zero differences are reported as `p = 1`, not an
  error.
- Bootstrap percentile CI (10,000 resamples of seeds, fixed RNG seed)
  as a cross-check on the t-based interval.
- Cohen's d for paired data: `mean(d) / std(d)`.
- McNemar's exact test on paired binary outcomes
  `score < THRESHOLD` (default 10) and `score >= 24`.

Holm is applied separately for each metric family (score, lives lost,
critical discards) and separately for each McNemar family.

Lives lost is `3 - lives_remaining`. Critical discards are summed
over players.

## How to rerun

From the repo root, with the project environment active:

```sh
python stats/run_selfplay.py --out-dir stats/results --n 1000
python stats/run_stat_tests.py --results-dir stats/results \
  --baseline baseline --out stats/output
```

`ACTIVE_AGENTS` and `DEPRECATED_AGENTS` are in `stats/config.py`.
Deprecated versions are off by default. V12 is always run when
present (sanity check against the published paired difference).

```sh
uv run pytest tests/test_stat_tests.py
```

## Methods paragraph

We compare each agent against the baseline using paired t-tests over
N = 1000 shared seeds, reporting the mean difference with a 95%
confidence interval. Because we make multiple comparisons, p-values
are adjusted with the Holm method. We confirm results with Wilcoxon
signed-rank tests and bootstrap confidence intervals.
