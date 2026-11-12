"""Build 3-player self-play teams. Does not modify player classes."""

from __future__ import annotations

import logging
from collections.abc import Callable

from stats.config import (
    INTEGER_VERSIONS,
    N_PLAYERS,
    PLAYER_NAMES,
    SKIP_REASONS,
    V12_ETA,
    V12_LAMBDA,
)

log = logging.getLogger("stats")

PlayerFactory = Callable[[str, int], object]


def _self_intentional(version: int) -> PlayerFactory:
    from players.self_intentional import SelfIntentionalPlayer

    def make(name: str, pnr: int) -> object:
        return SelfIntentionalPlayer(name, pnr, version=version)

    return make


def _hint_silence() -> PlayerFactory:
    from players.hint_silence import HintSilencePlayer

    def make(name: str, pnr: int) -> object:
        return HintSilencePlayer(name, pnr, eta=V12_ETA, lambda_=V12_LAMBDA)

    return make


def _case_based() -> PlayerFactory:
    from players.case_based import CaseBasedPlayer

    def make(name: str, pnr: int) -> object:
        return CaseBasedPlayer(name, pnr)

    return make


def _cooperative() -> PlayerFactory | None:
    try:
        from players.cooperative_hints import CooperativeHintPlayer
    except ImportError as exc:
        log.warning("V16 unavailable: %s", exc)
        return None

    def make(name: str, pnr: int) -> object:
        return CooperativeHintPlayer(name, pnr)

    return make


def resolve_factory(agent: str) -> tuple[PlayerFactory | None, str | None]:
    """Return (factory, skip_reason). skip_reason is set when the agent cannot run."""
    if agent in SKIP_REASONS:
        return None, SKIP_REASONS[agent]
    if agent == "baseline":
        return _self_intentional(0), None
    if agent == "V12":
        return _hint_silence(), None
    if agent == "case":
        return _case_based(), None
    if agent == "V16":
        factory = _cooperative()
        if factory is None:
            return (
                None,
                "players.cooperative_hints.CooperativeHintPlayer is not importable",
            )
        return factory, None
    if agent.startswith("V") and agent[1:].isdigit():
        version = int(agent[1:])
        if version not in INTEGER_VERSIONS:
            return None, f"{agent} is not an integer SelfIntentionalPlayer version"
        return _self_intentional(version), None
    return None, f"unknown agent {agent!r}"


def make_players(agent: str, n_players: int = N_PLAYERS) -> list[object]:
    factory, reason = resolve_factory(agent)
    if factory is None:
        raise RuntimeError(reason or f"cannot build {agent}")
    names = list(PLAYER_NAMES) + [f"P{i}" for i in range(len(PLAYER_NAMES), n_players)]
    return [factory(names[i], i) for i in range(n_players)]
