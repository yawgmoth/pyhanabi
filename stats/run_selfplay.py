#!/usr/bin/env python3
"""Run 3-player self-play and write compact per-seed CSVs.

Usage (from the repo root):
    python stats/run_selfplay.py --out-dir stats/results
    python stats/run_selfplay.py --out-dir stats/results --agent baseline --n 1000

Each game uses ``hana_sim.set_deck_seed(seed)`` and ``random.seed(seed)``
with seed = 1..N so later statistical tests can pair rows. Games are
sequential inside one process (the C++ deck seed is process-global).
Existing CSV rows are kept; missing seeds are filled in.
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stats.agents import make_players, resolve_factory  # noqa: E402
from stats.config import (  # noqa: E402
    ACTIVE_AGENTS,
    DEPRECATED_AGENTS,
    INCLUDE_DEPRECATED,
    INITIAL_LIVES,
    N_GAMES,
    N_PLAYERS,
    REPO_ROOT,
    REQUIRED_AGENTS,
    SKIP_REASONS,
)

log = logging.getLogger("stats")

CSV_FIELDS = ("seed", "score", "lives_remaining", "lives_lost", "critical_discards")


def _configured_agents(include_deprecated: bool) -> list[str]:
    seen: list[str] = []
    for name in REQUIRED_AGENTS + ACTIVE_AGENTS:
        if name not in seen:
            seen.append(name)
    if include_deprecated:
        for name in DEPRECATED_AGENTS:
            if name not in seen:
                seen.append(name)
    return seen


def _sum_critical(metric_dict: dict) -> int:
    raw = metric_dict.get("critical_discards") if metric_dict else None
    if raw is None:
        return 0
    if hasattr(raw, "values"):
        return int(sum(raw.values()))
    return int(sum(raw))


def play_one(
    agent: str, seed: int, n_players: int = N_PLAYERS
) -> dict[str, int | float]:
    import hana_sim

    from game import HanasimGame
    from utils import NullStream

    random.seed(seed)
    hana_sim.set_deck_seed(seed)
    players = make_players(agent, n_players=n_players)
    game = HanasimGame(players, NullStream(), post_move_metrics=True)
    score = game.run()
    lives = int(game.jlog["result"]["lives_remaining"])
    return {
        "seed": seed,
        "score": int(score),
        "lives_remaining": lives,
        "lives_lost": INITIAL_LIVES - lives,
        "critical_discards": _sum_critical(game.metric_dict),
    }


def _read_done(path: Path) -> set[int]:
    if not path.is_file():
        return set()
    done: set[int] = set()
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("seed"):
                done.add(int(row["seed"]))
    return done


def run_agent(
    agent: str,
    out_dir: Path,
    n: int,
    n_players: int,
) -> Path | None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    reason = SKIP_REASONS.get(agent)
    if reason:
        log.info("skipping %s: %s", agent, reason)
        return None
    _factory, skip = resolve_factory(agent)
    if skip:
        log.info("skipping %s: %s", agent, skip)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{agent}.csv"
    done = _read_done(path)
    seeds = [s for s in range(1, n + 1) if s not in done]
    log.info(
        "%s: %d/%d seeds already on disk, %d remaining -> %s",
        agent,
        len(done),
        n,
        len(seeds),
        path,
    )
    if not path.is_file():
        with path.open("w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
    if not seeds:
        return path

    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for i, seed in enumerate(seeds, start=1):
            row = play_one(agent, seed, n_players=n_players)
            writer.writerow(row)
            f.flush()
            if i % 50 == 0 or i == len(seeds):
                log.info(
                    "%s: finished seed %d (%d/%d this session)",
                    agent,
                    seed,
                    i,
                    len(seeds),
                )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "stats" / "results")
    parser.add_argument(
        "--n", type=int, default=N_GAMES, help="number of games / max seed"
    )
    parser.add_argument("--players", type=int, default=N_PLAYERS)
    parser.add_argument(
        "--agent",
        action="append",
        dest="agents",
        help="agent key (repeatable). Default: baseline, V12, and ACTIVE_AGENTS",
    )
    parser.add_argument(
        "--include-deprecated",
        action="store_true",
        default=INCLUDE_DEPRECATED,
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="parallel agent processes (C++ engine is per-process)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    agents = args.agents if args.agents else _configured_agents(args.include_deprecated)
    log.info("self-play agents: %s (jobs=%d)", ", ".join(agents), args.jobs)
    written = []
    skipped = []
    if args.jobs <= 1:
        results = [
            (agent, run_agent(agent, args.out_dir, args.n, args.players))
            for agent in agents
        ]
    else:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        ctx = multiprocessing.get_context("spawn")
        results = []
        with ProcessPoolExecutor(max_workers=args.jobs, mp_context=ctx) as pool:
            futs = {
                pool.submit(run_agent, agent, args.out_dir, args.n, args.players): agent
                for agent in agents
            }
            for fut in as_completed(futs):
                agent = futs[fut]
                try:
                    results.append((agent, fut.result()))
                except Exception:
                    log.exception("agent %s failed", agent)
                    results.append((agent, None))
                    skipped.append(f"{agent} (crashed)")
    for agent, path in results:
        if path is None:
            if agent not in [s.split()[0] for s in skipped]:
                skipped.append(agent)
        else:
            written.append(agent)
    log.info("wrote %s", ", ".join(written) or "(none)")
    if skipped:
        log.info("skipped %s", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
