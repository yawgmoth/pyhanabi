import json
import random
import os
import sys
import time
from typing import Any
import numpy
import io

LOG_DIR = "log"
LOG_JSON_DIR = "json"
LOW_MARKS_DIR = os.path.join(LOG_DIR, "low_scores")
HIGH_MARKS_DIR = os.path.join(LOG_DIR, "high_scores")

# Logs are classified by rank once the whole run is finished:
# - the lowest LOW_SCORE_FRACTION of games go to low_scores/ (1% of 1000 = 10 games)
# - the HIGH_SCORE_COUNT highest-scoring games go to high_scores/
# Ties are broken by game number, so exactly that many games are moved.
LOW_SCORE_FRACTION = 0.01
HIGH_SCORE_COUNT = 5

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LOW_MARKS_DIR, exist_ok=True)
os.makedirs(HIGH_MARKS_DIR, exist_ok=True)

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import hana_sim  # type: ignore
from hana_sim import PlayerName  # type: ignore

from game import HanasimGame, Game
from players import (
    Player,
    SelfIntentionalPlayerWithMemory,
    InnerStatePlayer,
    OuterStatePlayer,
    SelfRecognitionPlayer,
    IntentionalPlayer,
    SelfIntentionalPlayer,
    SelfIntentionalPlayerDetectDeadColors,
    SamplingRecognitionPlayer,
    TimedPlayer,
    LLMAgentPlayer,
    CaseBasedPlayer,
)
from players.hanasim import HanaSimPlayer
from utils import NullStream

random.seed(123)

player_types = {
    "random": Player,
    "inner": InnerStatePlayer,
    "outer": OuterStatePlayer,
    "self": SelfRecognitionPlayer,
    "intentional": IntentionalPlayer,
    "sample": SamplingRecognitionPlayer,
    "full": SelfIntentionalPlayer,
    "timed": TimedPlayer,
    "full-with-mem": SelfIntentionalPlayerWithMemory,
    "full-detect-dead": SelfIntentionalPlayerDetectDeadColors,
    "llm": LLMAgentPlayer,
    "case": CaseBasedPlayer,
}

names = ["Shangdi", "Yu Di", "Tian", "Nu Wa", "Pangu"]

# Per-game, per-player count metrics collected by HanasimGame when post_move_metrics is on.
# Key should exactly the same as in game.py
POST_MOVE_METRICS = [
    "critical_discards",
    "known_discards",
    "known_playable_plays",
    "has_playable",
    "known_unplayable_plays",
    "has_unplayable",
    "hint_frequency",
]


def make_player(player_type: str, player_id: int, version: int = 0 ) -> Player:
    if player_type in player_types:
        if version > 0 and player_type == "full":
            return player_types[player_type](names[player_id], player_id, version=version)
        return player_types[player_type](names[player_id], player_id)

    elif player_type.startswith("self("):
        other = player_type[5:-1]
        return SelfRecognitionPlayer(names[player_id], player_id, player_types[other])

    elif player_type.startswith("sample("):
        other = player_type[7:-1]
        if "," in other:
            othername_raw, maxtime_raw = other.split(",")
            othername = othername_raw.strip()
            maxtime = int(maxtime_raw.strip())
            return SamplingRecognitionPlayer(
                names[player_id], player_id, player_types[othername], maxtime=maxtime
            )
        return SamplingRecognitionPlayer(
            names[player_id], player_id, player_types[other]
        )

    else:
        # try to find a matching HanaSim player name
        try:
            normalized_name = player_type.strip().lower()
            for key in PlayerName.__members__:
                if normalized_name == key.lower():
                    return HanaSimPlayer(PlayerName.__members__[key], player_id)
        except KeyError:
            pass

        raise ValueError(f"Unknown player type: {player_type}")


def report_metrics(pts: list[int], players: list[Player], n: int,
                   post_move_metrics: bool=False, metrics:dict=None, prefix="plots/",
                   suffix = ""):
    """All end-of-run evaluation: summary statistics + histograms"""
    # If plots/ doesn't exist, create one
    if os.path.dirname(prefix):
        os.makedirs(os.path.dirname(prefix), exist_ok=True)
    saved = []

    # Scores: always reported
    scores = pd.Series(pts, name="score")
    print("\n=== Score distribution ===")
    print(scores.describe())

    # Save the score distribution
    fig, ax = plt.subplots(figsize=(6, 4))
    scores.hist(bins=range(0, 27), ax=ax, edgecolor="black")
    ax.set_xlabel("Final score")
    ax.set_ylabel("Number of games")
    ax.set_title(f"Score distribution over {n} games")
    fig.tight_layout()
    fig.savefig(f"{prefix}score_{suffix}.png", dpi=120)
    plt.close(fig)
    saved.append(f"{prefix}score_{suffix}.png")


    # Hint interpretation accuracy: per-game mean per player; NaN when a player had no hints that game
    cols = [f"Player {pl.pnr}" for pl in players]
    hint_accuracy_df = pd.DataFrame({
            cols[p]: [
                metrics["hint_interpreted_correctly"][g][p] / metrics["hints_received"][g][p] if metrics["hints_received"][g][p] > 0
                else numpy.nan
                for g in range(n)
            ]
            for p in range(len(players))
        })
    print("\n=== Hint Interpretation Accuracy (per-game mean) ===")
    print(hint_accuracy_df.describe())

    # Save the hint_accuracy distribution
    axes = hint_accuracy_df.hist(bins=20, figsize=(5 * len(players), 4),
                           edgecolor="black", layout=(1, len(players)))
    for ax in numpy.ravel(axes):
        ax.set_xlabel("Mean Hint Interpretation Accuracy per game")
        ax.set_ylabel("Number of games")
    plt.tight_layout()
    plt.savefig(f"{prefix}hint_interpretation_accuracy_{suffix}.png", dpi=120)
    plt.close("all")
    saved.append(f"{prefix}hint_interpretation_accuracy_{suffix}.png")

    # Post-move metrics: summarized and plotted iff enabled
    if post_move_metrics and metrics is not None:
        cols = [f"Player {pl.pnr}" for pl in players]

        # IPP: per-game mean per player; NaN when a player had no IPP data that game
        ipp_df = pd.DataFrame({
            cols[p]: [
                numpy.mean(metrics["ipp_list"][g][p]) if len(metrics["ipp_list"][g][p]) > 0
                else numpy.nan
                for g in range(n)
            ]
            for p in range(len(players))
        })
        print("\n=== IPP (per-game mean) ===")
        print(ipp_df.describe())

        # Save the ipp distribution
        axes = ipp_df.hist(bins=20, figsize=(5 * len(players), 4),
                           edgecolor="black", layout=(1, len(players)))
        for ax in numpy.ravel(axes):
            ax.set_xlabel("Mean IPP per game")
            ax.set_ylabel("Number of games")
        plt.tight_layout()
        plt.savefig(f"{prefix}ipp_{suffix}.png", dpi=120)
        plt.close("all")
        saved.append(f"{prefix}ipp_{suffix}.png")

        # Post-move metrics: one DataFrame per metric
        # rows = games, columns = players
        for name in POST_MOVE_METRICS:
            if name not in metrics: # error guard
                continue
            df = pd.DataFrame(metrics[name], columns=cols)
            print(f"\n=== {name} (per game) ===")
            print(df.describe())

            # Save the plot
            max_v = int(numpy.nanmax(df.to_numpy()))
            value_range = range(0, max_v + 1)

            fig, axes = plt.subplots(1, len(players), figsize=(5 * len(players), 4),
                                     sharey=True)
            for ax, col in zip(numpy.atleast_1d(axes), cols):
                counts = df[col].value_counts().reindex(value_range, fill_value=0)
                ax.bar(counts.index, counts.values, edgecolor="black")
                ax.set_xticks(list(value_range))
                ax.set_title(col)
                ax.set_xlabel(name.replace("_", " "))
            numpy.atleast_1d(axes)[0].set_ylabel("Number of games")
            fig.suptitle(f"{name} per game")
            fig.tight_layout()
            fig.savefig(f"{prefix}{name}_distribution_{suffix}.png", dpi=120)
            plt.close(fig)
            saved.append(f"{prefix}{name}_distribution_{suffix}.png")

    print("\nSaved:", *saved, sep="\n  ")


def classify_game_logs(game_logs: list[tuple[int, int, str]]):
    """Move the lowest- and highest-scoring game logs out of LOG_DIR.

    game_logs holds one (score, game number, log path) entry per game. The
    bottom LOW_SCORE_FRACTION of games are moved to LOW_MARKS_DIR and the top
    HIGH_SCORE_COUNT games to HIGH_MARKS_DIR; a game is never moved twice.
    """
    by_score = sorted(game_logs)  # ascending score, ties by game number
    n_low = max(1, round(len(by_score) * LOW_SCORE_FRACTION))
    low = by_score[:n_low]
    rest = by_score[n_low:]
    # highest score first; among equal scores, the earliest game wins
    high = sorted(rest, key=lambda x: (-x[0], x[1]))[:HIGH_SCORE_COUNT]

    for target_dir, selected in ((LOW_MARKS_DIR, low), (HIGH_MARKS_DIR, high)):
        for _, _, path in selected:
            os.replace(path, os.path.join(target_dir, os.path.basename(path)))

    if low:
        print(f"\nMoved {len(low)} lowest-scoring logs to {LOW_MARKS_DIR}/ "
              f"(scores {low[0][0]}-{low[-1][0]})")
    if high:
        print(f"Moved {len(high)} highest-scoring logs to {HIGH_MARKS_DIR}/ "
              f"(scores {high[-1][0]}-{high[0][0]})")


def main(args):
    post_move_metrics = True
    if not args:
        args = ["random"] * 3
    if args[0] == "trial":
        treatments = [
            ["intentional", "intentional"],
            ["intentional", "outer"],
            ["outer", "outer"],
        ]
        # [["sample(intentional, 50)", "sample(intentional, 50)"], ["sample(intentional, 100)", "sample(intentional, 100)"]] #, ["self(intentional)", "self(intentional)"], ["self", "self"]]
        print(treatments)
        for i in range(int(args[1])):
            result = []
            times = []
            avg_times: list[float] = []
            ipp_lists: list[list[list[float]]] = []
            critical_discards: list[list[int]] = []
            known_discards: list[list[int]] = []
            known_playable_plays: list[list[int]] = []
            has_playable: list[list[int]] = []
            known_unplayable_plays: list[list[int]] = []
            has_unplayable: list[list[int]] = []
            hint_frequencies: list[list[int]] = []
            hint_possible: list[list[int]] = []
            hints_received: list[list[int]] = []
            hints_interpreted_correctly: list[list[int]] = []
            print("trial", i + 1)
            for t in treatments:
                random.seed(i)
                trial_players = []
                for j, player in enumerate(t):
                    trial_players.append(make_player(player, j))
                # TODO: change back or add flag
                # g = Game(trial_players, NullStream())
                g = HanasimGame(trial_players, NullStream(), post_move_metrics)



                t0 = time.time()
                result.append(g.run())

                times.append(time.time() - t0)

                if post_move_metrics:
                    metrics = g.metric_dict
                    ipp_lists.append(metrics["ipp_list"])
                    critical_discards.append(metrics["critical_discards"])
                    known_discards.append(metrics["known_discards"])
                    known_playable_plays.append(metrics["known_playable_plays"])
                    has_playable.append(metrics["has_playable"])
                    known_unplayable_plays.append(metrics["known_unplayable_plays"])
                    has_unplayable.append(metrics["has_unplayable"])
                    hint_frequencies.append(metrics["hint_frequency"])
                    hint_possible.append(metrics["hint_possible"])
                    hints_received.append(metrics["hints_received"])
                    hints_interpreted_correctly.append(metrics["hint_interpreted_correctly"])
                # TODO: change back or add flag
                # avg_times.append(times[-1] * 1.0 / g.turn)
                print(
                    ".",
                )
            print()
            print("scores:", result)
            print("times:", times)
            print("avg times:", avg_times)

            if post_move_metrics:
                for i, player in enumerate(treatments):
                    total_valid_ipp = 0
                    sum_ipp = 0
                    for j in range(int(args[1])):
                        if len(ipp_lists[j][i]) > 0:
                            total_valid_ipp += 1
                            sum_ipp += numpy.mean(ipp_lists[j][i])

                    avg_ipp = sum_ipp / total_valid_ipp if total_valid_ipp > 0 else None


                    avg_critical_discards = sum(
                        critical_discards[j][i] for j in range(int(args[1]))
                    ) / int(args[1])

                    avg_known_discards = sum(
                        known_discards[j][i] for j in range(int(args[1]))
                    ) / int(args[1])

                    if sum(has_playable[j][i] for j in range(int(args[1]))) == 0:
                        avg_known_playable_plays = 0
                    else:
                        avg_known_playable_plays = sum(
                            known_playable_plays[j][i] for j in range(int(args[1]))
                        ) / sum(has_playable[j][i] for j in range(int(args[1])))

                    if sum(has_unplayable[j][i] for j in range(int(args[1]))) == 0:
                        avg_known_unplayable_plays = 0
                    else:
                        avg_known_unplayable_plays = sum(
                            known_unplayable_plays[j][i] for j in range(int(args[1]))
                        ) / sum(has_unplayable[j][i] for j in range(int(args[1])))

                    if sum(hint_possible[j][i] for j in range(int(args[1]))) == 0:
                        avg_hint_frequency = 0
                    else:
                        avg_hint_frequency = sum(
                            hint_frequencies[j][i] for j in range(int(args[1]))
                        ) / sum(hint_possible[j][i] for j in range(int(args[1])))

                    if sum(hints_received[j][i] for j in range(int(args[1]))) == 0:
                        avg_hint_interpretation = 0
                    else:
                        avg_hint_interpretation = sum(
                            hints_interpreted_correctly[j][i] for j in range(int(args[1]))
                        ) / sum(hints_received[j][i] for j in range(int(args[1])))

                    if avg_ipp is None:
                        print(f"IPP for {player}: No valid data")
                    else:
                        print(f"Average valid IPP count for {player}: {total_valid_ipp} out of {int(args[1])}")
                        print(f"IPP for {player}: {avg_ipp}")

                    print(f"Average critical discards for {player}: {avg_critical_discards}")
                    print(f"Average known discards for {player}: {avg_known_discards}")
                    print(f"Average known playable plays for {player}: {avg_known_playable_plays}")
                    print(f"Average known unplayable plays for {player}: {avg_known_unplayable_plays}")
                    print(f"Average hint frequency for {player}: {avg_hint_frequency}")
                    print(f"Average hint interpretation accuracy for {player}: {avg_hint_interpretation}")

        return


    # -------- Non-trial Simulations: --------
    players: list[Player] = []

    for i, a in enumerate(args):
        if a.startswith("full/"):
            agent = a.split("/")
            v = int(agent[1]) if len(agent) > 1 else 0
            players.append(make_player(agent[0], i, v))
            print(f"Player {i}: {agent[0]} (version {v})")
        else:
            players.append(make_player(a, i))

    n = 1000
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    pts = []
    game_logs: list[tuple[int, int, str]] = []  # (score, game number, log path)
    all_metrics = {name: [] for name in ["ipp_list", "hint_interpreted_correctly", "hints_received"] + POST_MOVE_METRICS}

    for i in list(range(n)):
        # Display in terminal every 100 game
        if (i + 1) % 100 == 0:
            print("Starting game", i + 1)
        random.seed(i + 1)
        hana_sim.set_deck_seed(i + 1)

        game_log = io.StringIO()     # empty buffer for this game
        print(f"{len(players)} players: {', '.join(args)}",
              file=game_log)
        print(file=game_log)
        # TODO: change back or add flag
        # g = Game(players, game_log)
        g = HanasimGame(players, game_log, post_move_metrics)
        score = g.run()

        # every log is written to LOG_DIR; classify_game_logs() moves the
        # lowest/highest-scoring ones once all games are done
        log_path = os.path.join(LOG_DIR, f"{len(players)}p{i + 1:04d}_{timestamp}.txt")
        with open(log_path, "w") as f:
            f.write(game_log.getvalue())
        game_log.close()
        game_logs.append((score, i + 1, log_path))

        json_path = os.path.join(LOG_JSON_DIR, f"{len(players)}p{i + 1:04d}_{timestamp}.json")
        with open(json_path, "w") as f:
            json.dump(g.jlog, f, indent=2)


        pts.append(score)

        if post_move_metrics:
            for name in all_metrics:
                if name == "ipp_list":
                    raw = g.metric_dict.get(name, [[] for _ in players])
                    all_metrics[name].append([raw[p.pnr] for p in players])
                else:
                    raw = g.metric_dict.get(name, None)
                    if raw is None:
                        all_metrics[name].append([0] * len(players))
                    else:
                        all_metrics[name].append([raw[p.pnr] for p in players])

    if n < 10:
        print(pts)

    classify_game_logs(game_logs)

    report_metrics(pts, players, n,
                   post_move_metrics=post_move_metrics,
                   metrics=all_metrics if post_move_metrics else None,
                   suffix=f"{timestamp}")


if __name__ == "__main__":
    main(sys.argv[1:])
