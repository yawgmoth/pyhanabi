"""Load per-game rows from compact CSVs or hanabi.py json/log dumps."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd

from stats.config import INITIAL_LIVES

log = logging.getLogger("stats")

FNAME_RE = re.compile(
    r"^(?P<nplayers>\d+)p(?P<game>\d{4})_(?P<ts>\d{8}_\d{6})\.(?P<ext>json|txt)$"
)
HEADER_RE = re.compile(r"^(\d+)\s+players:\s*(.+)$")
CRIT_RE = re.compile(r"Critical Discards:\s*(\d+)")


def _standardize(df: pd.DataFrame, agent: str) -> pd.DataFrame:
    out = df.copy()
    if "seed" not in out.columns:
        raise ValueError(f"{agent}: missing seed column")
    if "score" not in out.columns:
        raise ValueError(f"{agent}: missing score column")
    out["seed"] = out["seed"].astype(int)
    out["score"] = out["score"].astype(float)
    if "lives_remaining" in out.columns and "lives_lost" not in out.columns:
        out["lives_lost"] = INITIAL_LIVES - out["lives_remaining"].astype(float)
    if "lives_lost" not in out.columns:
        out["lives_lost"] = pd.NA
    if "critical_discards" not in out.columns:
        out["critical_discards"] = pd.NA
    out = out.sort_values("seed").drop_duplicates("seed", keep="last")
    out["agent"] = agent
    return out.reset_index(drop=True)


def load_compact_csv(path: Path, agent: str | None = None) -> pd.DataFrame:
    name = agent if agent is not None else path.stem
    df = pd.read_csv(path)
    return _standardize(df, name)


def load_results_dir(results_dir: Path) -> dict[str, pd.DataFrame]:
    """Load ``<agent>.csv`` files from a compact results directory."""
    results_dir = Path(results_dir)
    out: dict[str, pd.DataFrame] = {}
    if not results_dir.is_dir():
        return out
    for path in sorted(results_dir.glob("*.csv")):
        agent = path.stem
        try:
            out[agent] = load_compact_csv(path, agent)
            log.info("loaded %s: %d games from %s", agent, len(out[agent]), path)
        except (ValueError, pd.errors.EmptyDataError) as exc:
            log.warning("skipping %s: %s", path, exc)
    return out


def parse_run_header(text: str) -> tuple[int, str] | None:
    """Return (n_players, agent_label) from the first line of a text log."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = HEADER_RE.match(line)
        if not m:
            return None
        n_players = int(m.group(1))
        parts = [p.strip() for p in m.group(2).split(",")]
        if not parts:
            return None
        if len(set(parts)) != 1:
            log.warning("mixed agents in log header: %s", parts)
            return None
        return n_players, _header_to_agent(parts[0])
    return None


def _header_to_agent(token: str) -> str:
    token = token.strip()
    if token == "full":
        return "baseline"
    if token.startswith("full/"):
        return f"V{token.split('/', 1)[1]}"
    if token == "case":
        return "case"
    return token


def critical_discards_from_log(text: str) -> int | None:
    found = CRIT_RE.findall(text)
    if not found:
        return None
    return int(sum(int(x) for x in found))


def load_json_run(
    json_dir: Path, timestamp: str, log_dir: Path | None = None
) -> pd.DataFrame:
    """Load one hanabi.py dump (``{n}p{game}_{timestamp}.json``) as a per-seed table."""
    json_dir = Path(json_dir)
    rows = []
    agent = None
    n_players = None
    files = sorted(json_dir.glob(f"*_{timestamp}.json"))
    if not files:
        raise FileNotFoundError(
            f"no json files matching *_{timestamp}.json in {json_dir}"
        )
    for path in files:
        m = FNAME_RE.match(path.name)
        if not m:
            log.warning("unrecognised json name: %s", path.name)
            continue
        seed = int(m.group("game"))
        n_players = int(m.group("nplayers"))
        payload = json.loads(path.read_text())
        result = payload.get("result") or {}
        score = result.get("score")
        lives = result.get("lives_remaining")
        crit = None
        if log_dir is not None:
            log_path = _matching_log(Path(log_dir), path.stem)
            if log_path is not None:
                text = log_path.read_text(encoding="utf-8", errors="replace")
                crit = critical_discards_from_log(text)
                parsed = parse_run_header(text)
                if parsed is not None:
                    n_players, agent = parsed
        lives_lost = None if lives is None else INITIAL_LIVES - float(lives)
        rows.append(
            {
                "seed": seed,
                "score": score,
                "lives_remaining": lives,
                "lives_lost": lives_lost,
                "critical_discards": crit,
                "n_players": n_players,
            }
        )
    if not rows:
        raise FileNotFoundError(f"no parseable games for timestamp {timestamp}")
    label = agent or f"run_{timestamp}"
    df = _standardize(pd.DataFrame(rows), label)
    df["n_players"] = n_players
    df["timestamp"] = timestamp
    return df


def _matching_log(log_dir: Path, stem: str) -> Path | None:
    direct = log_dir / f"{stem}.txt"
    if direct.is_file():
        return direct
    for sub in ("low_scores", "high_scores", "max_score"):
        cand = log_dir / sub / f"{stem}.txt"
        if cand.is_file():
            return cand
    return None


def list_json_timestamps(json_dir: Path) -> list[str]:
    json_dir = Path(json_dir)
    ts = []
    for path in json_dir.glob("*.json"):
        m = FNAME_RE.match(path.name)
        if m:
            ts.append(m.group("ts"))
    return sorted(set(ts))
