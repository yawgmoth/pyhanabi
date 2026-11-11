#!/usr/bin/env python3

"""
Log Parser Command Line Interface.

Usage examples:

    python log_analyzer.py --help
"""

import argparse
import collections
import re
import json
import ast
from pathlib import Path
from typing import Tuple, List

ALLOWED_SUBDIRS = {"low_scores", "high_scores", "max_score"}
CARD_COUNTS = {
    1: 3,
    2: 2,
    3: 2,
    4: 2,
    5: 1
}
END_REASONS = ["deck exhausted", "out of lives", "board completed"]

# ---------------------------------------------------------------------------
# Command: critical_discards
# ---------------------------------------------------------------------------

def get_critical_discards_from_file(path: Path) -> Tuple[int, int]:
    """
    Return an (int, int) tuple:
    - result[0] is the total number of discards
    - results[1] is the number of critical discards
    """
    assert path.is_file(), f"The path provided is not a file: {path}"
    with open(path, "r") as f:
        lines = f.readlines()
        total_discards = sum(1 for line in lines if "Move" in line and "discards" in line)
        critical_discards_lines = [line for line in lines if "Critical Discards" in line]
        critical_discards = 0
        for line in critical_discards_lines:
            match = re.search(r"Critical Discards:\s*(\d+)", line)
            assert match
            critical_discards += int(match.group(1))

    return total_discards, critical_discards


def report_critical_discards(path: Path) -> None:
    """
    Report stats on critical discards.
    Is path points to a single log file, report stats on the single game.
    If path points to a directory of log files, report aggregate stats on all games.
    """
    if path.is_file():
        print(f"Reporting critical discards for file: {path}")
        total_discards, critical_discards = get_critical_discards_from_file(path)
        print("Total discards:", total_discards)
        print("Critical discards:", critical_discards)
        print("Critical discards ratio:", critical_discards / total_discards)

    elif path.is_dir():
        print(f"Reporting aggregate critical discards for directory {path}")
        aggregate_total_discards, aggregate_critical_discards = 0, 0
        game_count = 0
        for file in path.rglob("*"):
            if file.is_dir():
                assert file.name in ALLOWED_SUBDIRS, (f"The path under directory {path} is not a file: {file}, "
                                                      f"and does not correspond to an allowed subdirectory name")
                continue
            game_count += 1
            total_discards, critical_discards = get_critical_discards_from_file(file)
            aggregate_total_discards += total_discards
            aggregate_critical_discards += critical_discards
        print("Aggregate total discards:", aggregate_total_discards)
        print("Aggregate critical discards:", aggregate_critical_discards)
        print("Aggregate critical discards ratio:", aggregate_critical_discards / aggregate_total_discards)
        print("Number of games:", game_count)
        print("Average total discards per game:", aggregate_total_discards / game_count)
        print("Average critical discards per game:", aggregate_critical_discards / game_count)

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: hint_types
# ---------------------------------------------------------------------------

def get_hint_types_from_json(path: Path) -> Tuple[int, int, int, int]:
    """
    Given a JSON file representing a game log, return a tuple where:
    - result[0] is the total number of hints given in the game
    - result[1] is the number of intentional hints given in the game
    - result[2] is the number of redundant hints given in the game
    - result[3] is the number of random hints given in the game
    """
    assert path.is_file() and path.suffix.lower() == ".json", f"The path provided is not a JSON file: {path}"
    with open(path, "r") as f:
        json_data = json.load(f)
        assert type(json_data) == dict, f"Impossible to parse the JSON file into a dict: {path}"
        turns = 1
        total_hints = 0
        intentional_hints = 0
        redundant_hints = 0
        random_hints = 0
        for turn in json_data["actions"]:
            action = turn[f"turn_{turns}"]["action"]
            # validate the logic in the log
            # 1. there are valid intentional hints ==> we either hint the color or the rank
            if action["valid_hints"]:
                assert action["type"] == "HINT_COLOR" or action["type"] == "HINT_NUMBER", f"file: {path}"
                total_hints += 1
                intentional_hints += 1
            # 2. no valid intentional hints ==> we either have redundant hints, or we chose to play or discard
            else:
                if action["redundant_hints"] and (action["type"] == "HINT_COLOR" or action["type"] == "HINT_NUMBER"):
                    total_hints += 1
                    redundant_hints += 1
                elif action["type"] == "HINT_COLOR" or action["type"] == "HINT_NUMBER":
                    total_hints += 1
                    random_hints += 1
            turns += 1

    return total_hints, intentional_hints, redundant_hints, random_hints


def report_hint_types(path: Path) -> None:
    """
    Generate a summary of the hint types provided in the JSON logs.
    Is path points to a single log file, report hint details on the single game.
    If path points to a directory of log files, report aggregate hint details on all games.
    """
    if path.is_file():
        print(f"Reporting hint details on file: {path}")
        total_hints, intentional_hints, redundant_hints, random_hints = get_hint_types_from_json(path)
        print("Total hints:", total_hints)
        print("Intentional hints:", intentional_hints)
        print("Redundant hints:", redundant_hints)
        print("Random hints:", random_hints)
        print("Intentional hints ratio:", intentional_hints / total_hints)
        print("Redundant hints ratio:", redundant_hints / total_hints)

    elif path.is_dir():
        print(f"Reporting aggregate hint details for directory: {path}")
        aggregate_total_hints, aggregate_intentional_hints, aggregate_redundant_hints, aggregate_random_hints = 0, 0, 0, 0
        game_count = 0
        for file in path.iterdir():
            assert file.is_file()
            total_hints, intentional_hints, redundant_hints, random_hints = get_hint_types_from_json(file)
            aggregate_total_hints += total_hints
            aggregate_intentional_hints += intentional_hints
            aggregate_redundant_hints += redundant_hints
            aggregate_random_hints += random_hints
            game_count += 1

        print("Aggregate total hints", aggregate_total_hints)
        print("Aggregate intentional hints", aggregate_intentional_hints)
        print("Aggregate redundant hints", aggregate_redundant_hints)
        print("Aggregate random hints", aggregate_random_hints)
        print("Total games:", game_count)
        print("Intentional hint ratio over all games:", aggregate_intentional_hints / aggregate_total_hints)
        print("Redundant hint ratio over all games:", aggregate_redundant_hints / aggregate_total_hints)
        print("Random hint ratio over all games:", aggregate_random_hints / aggregate_total_hints)

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: third_player_hints
# ---------------------------------------------------------------------------
def is_critical_discard(move_info: list[str]) -> bool:
    """
    Takes in a set of move information form a log file (a single paragraph from a move file),
    and determines whether the discard was critical.
    Preconditions:
     - the move must refer to a discard move
    Returns: whether the discard was critical
    """
    move_line = move_info[0]
    assert "discards" in move_line
    trash_line = move_info[1]
    assert "Trash" in trash_line
    trash = trash_line.strip().removeprefix("Trash: ").split(", ")
    card_regex = re.compile(r'\b(white|red|blue|green|yellow) [1-5]\b')
    match = card_regex.search(move_line)
    assert match
    discarded_card = match.group(0)
    # int(discarded_card[-1]) gets the rank of the discard
    assert trash.count(discarded_card) <= CARD_COUNTS[int(discarded_card[-1])]
    return trash.count(discarded_card) == CARD_COUNTS[int(discarded_card[-1])]


def get_third_player_hint_info_from_file(path: Path) -> Tuple[int, int, int, int]:
    """
    Get details on "third player hints" from a given file. A third player hint is a hint given by Player A to Player C.
    We are specifically interested in the cases of third player hints that cause Player B to take a bad action.
    - result[0] is the total number of hints given
    - result[1] is the number of third player hints
    - result[2] is the number of times a third player hints causes Player B to misplay
    - result[3] is the number of times a third player hint causes Player B to discard a critical card
    """
    assert path.is_file(), f"The path provided is not a file: {path}"
    with open(path, "r") as f:
        moves = []
        curr_move = []
        for line in f.readlines():
            if "Move" in line:
                if curr_move:
                    moves.append(curr_move)
                curr_move = [line]
            elif "Trash:" in line:
                curr_move.append(line)
        # Don't forget to append the last move!
        if curr_move:
            moves.append(curr_move)

    total_hints = 0
    third_player_hints = 0
    misplays_after_third_player_hints = 0
    critical_discards_after_third_player_hints = 0

    for i in range(0, len(moves) - 1):
        curr_move_info = moves[i]
        next_move_info = moves[i + 1]

        # 1. Find the total number of hints
        # move[0] is the line that looks like this "Move #: <move description>"
        curr_move = curr_move_info[0]
        assert "Move" in curr_move, curr_move
        if "hints" in curr_move:
            total_hints += 1

            # 2. Find the cases where we have third player hints
            match = re.search(r"Player (\d+) hints Player (\d+)", curr_move)
            assert match is not None
            curr_player = int(match.group(1))
            hinted_player = int(match.group(2))
            num_players = 3  # Note: this would have to change in 4+ player scenario
            if (curr_player + 2) % num_players == hinted_player:  # This defines a "third player hint"
                third_player_hints += 1

                # 3. Find the cases where the third player hint causes player B to do "bad moves"
                next_move = next_move_info[0]
                assert "Move" in next_move
                # 3a. Find the cases where the third player hint causes a misplay
                if "plays" in next_move and "successfully" not in next_move:
                    misplays_after_third_player_hints += 1
                # 3b. Find the cases where the third player hint causes the discard of a critical card
                elif "discards" in next_move and is_critical_discard(next_move_info):
                    critical_discards_after_third_player_hints += 1

    return total_hints, third_player_hints, misplays_after_third_player_hints, critical_discards_after_third_player_hints


def report_third_player_hints(path: Path) -> None:
    """
    Report information on the scenario where the current player hints the player after the next ("third player hints").
    The information provided is as follows:
    - Total number of hints given
    - Number of times a third player hint is provided
    - Number of times a third player hint causes the player in between to misplay
    - Number of times a third player hint causes the player in between to discard a critical card
    """
    if path.is_file():
        print(f"Reporting third player hint details on file: {path}")
        total_hints, third_player_hints, misplays, critical_discards = get_third_player_hint_info_from_file(path)
        print("Total number of hints:", total_hints)
        print("Number of third player hints:", third_player_hints)
        print("Ratio of third player hints over all hints:", third_player_hints / total_hints)
        print("Number of times a third player hint which caused Player B to misplay:", misplays)
        print("Number of times a third player hint which caused a critical discard in Player B:", critical_discards)
        try:
            print("Ratio of third player hints which caused a misplay:", misplays / third_player_hints)
            print("Ratio of third player hints which caused a critical discard:", critical_discards / third_player_hints)
        except ZeroDivisionError:
            raise "No third player hints were found"

    elif path.is_dir():
        print(f"Reporting third player hint details on all log files in the directory: {path}")
        game_count = 0
        aggregate_total_hints = 0
        aggregate_third_player_hints = 0
        aggregate_misplays = 0
        aggregate_critical_discards = 0
        for file in path.rglob("*"):
            if file.is_dir():
                assert file.name in ALLOWED_SUBDIRS, (f"The path under directory {path} is not a file: {file}, "
                                                      f"and does not correspond to an allowed subdirectory name")
                continue
            game_count += 1
            total_hints, third_player_hints, misplays, critical_discards = get_third_player_hint_info_from_file(file)
            aggregate_total_hints += total_hints
            aggregate_third_player_hints += third_player_hints
            aggregate_misplays += misplays
            aggregate_critical_discards += critical_discards
        print("Number of games:", game_count)
        print("Aggregate total hints:", aggregate_total_hints)
        print("Aggregate third player hints:", aggregate_third_player_hints)
        try:
            print("Ratio of total hints which are third player hints:", aggregate_third_player_hints / aggregate_total_hints)
        except ZeroDivisionError:
            raise ValueError("No total hints were found")
        print("Aggregate misplays:", aggregate_misplays)
        print("Aggregate critical discards:", aggregate_critical_discards)
        try:
            print("Ratio of third player hints which caused a misplay:", aggregate_misplays / aggregate_third_player_hints)
            print("Ratio of third player hints which caused a critical discard:", aggregate_critical_discards / aggregate_third_player_hints)
        except ZeroDivisionError:
            raise ValueError("No third player hints were found")

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: compare_corresponding_games
# ---------------------------------------------------------------------------
def extract_score_from_file(path: Path) -> int:
    """Extract game score from the log file at path."""
    assert path.is_file(), f"Path does not exist: {path}"
    final_score_pattern = re.compile(r"Final Score: ([0-9]+)")
    final_score = None
    with open(path, "r") as f:
        for line in f:
            match = final_score_pattern.search(line)
            if match:
                final_score = match.group(1)
    assert final_score
    return int(final_score)


def get_stats_for_directories(base_path: Path, new_path: Path, verbose) -> Tuple[int, int, int, List[str], List[str]]:
    """
    Compare corresponding files base_path and new_path.
    For each corresponding file, collect information on:
     - how many (and which) games performed better than the base_path
     - how many (and which) games performed worse than the new_path
     - how many games how many games had the same final score
    Details on the return value:
     - result[0] is the game count
     - result[1] is the number of games where the new does better than the base
     - result[2] is the number of games where the new does worse than the base
     - result[3] is le list of games where the new does better than the base
     - result[4] is the list of games where the new does worse than the base
    """
    game_count = 0
    worse_score_game_count = 0
    worse_score_games = []
    better_score_game_count = 0
    better_score_games = []
    for base_file in base_path.rglob("*"):
        if base_file.is_dir():
            assert base_file.name in ALLOWED_SUBDIRS, (f"The path under directory {base_path} is not a file: {base_file}, "
                                                       f"and does not correspond to an allowed subdirectory name")
            continue

        # Get corresponding new_path
        filename_regex = re.compile(r'^(\d+p\d{4})_\d{8}_\d{6}\.txt$')
        game_str_match = filename_regex.match(base_file.name)
        assert game_str_match, f"The base file name {base_file.name} does not match the expected structure"
        game_str = game_str_match.group(1)
        new_file_pattern = game_str + "_*.txt"
        new_file_pattern_matches = list(new_path.rglob(new_file_pattern))
        assert len(new_file_pattern_matches) == 1

        # Now you can get the scores
        base_score = extract_score_from_file(base_file)
        new_score = extract_score_from_file(new_file_pattern_matches[0])
        game_count += 1
        if new_score < base_score:
            worse_score_game_count += 1
            if verbose:
                worse_score_games.append(game_str)
        elif new_score > base_score:
            better_score_game_count += 1
            if verbose:
                better_score_games.append(game_str)

    return game_count, better_score_game_count, worse_score_game_count, better_score_games, worse_score_games


def compare_corresponding_games(base_path: Path, new_path: Path, verbose=False) -> None:
    """Print final score performance comparison for corresponding games in base_path and new_path"""
    if base_path.is_file():
        assert new_path.is_file(), "Make sure that new_path exists and points to a file, since base_path points to a file"
        if verbose:
            print("WARNING: verbose mode has no effect when comparing individual files. The argument is being ignored")
        base_score = extract_score_from_file(base_path)
        new_score = extract_score_from_file(new_path)
        if base_score > new_score:
            print(f"SAD :( The new score is {new_score}, while the base score is {base_score}")
        elif base_score == new_score:
            print(f"GOOD, the base and the new have the same score: {base_score}")
        else:
            print(f"YAY! The new score is {new_score} while the base score was {base_score}")
    elif base_path.is_dir():
        assert new_path.is_dir(), "Make sure that new_path exists and points to a directory, since base_path points to a directory"
        (game_count,
         better_score_game_count,
         worse_score_game_count,
         better_score_games,
         worse_score_games) = get_stats_for_directories(base_path, new_path, verbose)
        print(f"Total number of games: {game_count}")
        print(f"Number of games where the new performs better than the base {better_score_game_count}")
        if verbose:
            print(f"Game IDs where the new performs better than the base {better_score_games}")
        print(f"Number of games where the new performs worse than the base {worse_score_game_count}")
        if verbose:
            print(f"Game IDs where the new performs worse than the base {worse_score_games}")
    else:
        raise ValueError(f"The base path does not exist. base_path: {base_path}")


# ---------------------------------------------------------------------------
# Command: lost_lives
# ---------------------------------------------------------------------------
def get_lives_remaining_from_file(path: Path) -> int:
    """Get the number of lives remaining at the end of a game for the game log"""
    assert path.is_file(), f"The provided path is not a file: {path}"
    initial_lives = 3
    with open(path, "r") as f:
        lines = f.readlines()
    lives_lost = sum(1 for line in lines if "and it failed" in line)
    assert lives_lost <= initial_lives
    return initial_lives - lives_lost


def report_lost_lives_info(path: Path, verbose=False) -> None:
    """
    Report information on lives lost during the games
    """
    if path.is_file():
        print(f"Reporting the number of lives left for file: {path}")
        lives_left = get_lives_remaining_from_file(path)
        if lives_left > 0:
            print("The deck exhausted in this game!")
            print(f"Number of lives remaining at the end of the game: {lives_left}")
        else:
            print(f"There were {lives_left} lives left at the end of this game. "
                  f"The players lost the game without exhausting the deck")

    elif path.is_dir():
        print(f"Reporting aggregate information on lives remaining for the games at {path}")
        game_count = 0
        total_lives_left = 0
        lost_games_count = 0
        lost_games = []
        for file in path.rglob("*.txt"):
            if file.is_dir():
                assert file.name in ALLOWED_SUBDIRS, (f"The path under directory {path} is not a file: {file}, "
                                                      f"and does not correspond to an allowed subdirectory name")
                continue
            game_count += 1
            lives_left = get_lives_remaining_from_file(file)
            total_lives_left += lives_left
            if lives_left == 0:
                lost_games_count += 1
                if verbose:
                    lost_games.append(file.name)
        print(f"Number of games: {game_count}")
        print(f"Average number lives left across all games: {total_lives_left / game_count}")
        print(f"Number of games where the deck was not exhausted (all lives lost): {lost_games_count}")
        print(f"Average number of lives left across games where the deck was exhausted: {total_lives_left / (game_count - lost_games_count)}")
        if verbose:
            print(f"Games where the players lost all lives: {lost_games}")

    else:
        raise ValueError(f"Path does not exist. path: {path}")


# ---------------------------------------------------------------------------
# Command: report_potential_score_loss
# ---------------------------------------------------------------------------

def get_critical_card_list_from_file(path: Path) -> None:
    """
    Return a list of tuples (colour, rank) of the critical cards discarded.
    """
    assert path.is_file(), f"The path provided is not a file: {path}"
    with open(path, "r") as f:
        lines = f.readlines()

    critical_discards_line = [line for line in lines if line.startswith("Critical cards discarded:")]
    if not critical_discards_line:
        raise ValueError(f"No critical-card summary found in {path}")

    return ast.literal_eval(
        critical_discards_line[-1].split(":", 1)[1].strip()
    )


def get_estimate_critical_and_overall_score_loss_from_file(path: Path) -> int:
    """
    Estimate the potential score loss from critical card discards and the score
    loss overall.
    """
    assert path.is_file(), f"The path provided is not a file: {path}"

    with open(path, "r") as f:
        lines = f.readlines()

    # Get the final score from the game log.
    score_lines = [
        line for line in lines
        if line.startswith("Final Score:")
    ]
    if not score_lines:
        raise ValueError(f"No Final Score line found in {path}")

    final_score = int(score_lines[-1].split(":", 1)[1].strip())
    overall_score_loss = 25 - final_score

    # Get the last board state recorded in the game.
    board_lines = [
        line for line in lines
        if line.startswith("Board:")
    ]
    if not board_lines:
        raise ValueError(f"No Board line found in {path}")

    board = {}
    for entry in board_lines[-1].strip()[len("Board:"):].split(","):
        match = re.fullmatch(
            r"\s*(green|yellow|white|blue|red)\s+(\d+)\s*",
            entry,
        )
        if not match:
            raise ValueError(f"Cannot parse board entry: {entry}")

        color, height = match.groups()
        board[color] = int(height)

    # get all the critical cards discarded
    critical_cards = get_critical_card_list_from_file(path)
    score_loss = estimate_blocked_score_loss(critical_cards, board)

    return score_loss, overall_score_loss


def estimate_blocked_score_loss(critical_cards, board: dict) -> int:
    """
    Estimate the score lost because the given critical cards left the game:
    for each colour, every rank from the lowest lost critical card up to 5 can no longer be played.
    """
    lowest_blocked_rank = {}
    for col, rank in critical_cards:
        if rank > board[col]:
            if (
                    col not in lowest_blocked_rank
                    or rank < lowest_blocked_rank[col]
            ):
                lowest_blocked_rank[col] = rank

    return sum(6 - rank for rank in lowest_blocked_rank.values())


def report_potential_score_loss(path: Path) -> None:
    """
    Report the score losses overall and due to critical discards.
    """
    if path.is_file():
        critical, overall_loss = get_estimate_critical_and_overall_score_loss_from_file(path)
        print("Estimated potential critical score loss:", critical)
        print("Overall score loss:", overall_loss)
        return

    if not path.is_dir():
        raise ValueError(f"Path does not exist: {path}")

    files = [
        file for file in path.rglob("*")
        if file.is_file()
    ]

    if not files:
        print("No game logs found.")
        return

    critical_loss = sum(
        get_estimate_critical_and_overall_score_loss_from_file(file)[0]
        for file in files
    )
    total_loss = sum(
        get_estimate_critical_and_overall_score_loss_from_file(file)[1]
        for file in files
    )

    print("Games analyzed:", len(files))
    print("Total score loss:", total_loss)
    print("Average total score loss per game:",
          total_loss / len(files))
    print("Total estimated critical discard potential score loss:", critical_loss)
    print("Average estimated critical discard potential score loss per game:",
          critical_loss / len(files))


# ---------------------------------------------------------------------------
# Command: end_reasons
# ---------------------------------------------------------------------------

def get_end_reason_from_file(path: Path) -> str:
    """
    Return why the game in the given log file ended: one of END_REASONS,
    or "unknown" for logs written before the end reason was recorded.
    """
    assert path.is_file(), f"The path provided is not a file: {path}"
    with open(path, "r") as f:
        for line in f:
            if line.startswith("End reason:"):
                return line.removeprefix("End reason:").strip()
    return "unknown"


def report_end_reasons(path: Path) -> None:
    """
    Report why games ended (deck exhausted, out of lives, board completed).
    If path points to a single log file, report the end reason of the single game.
    If path points to a directory of log files, report counts and ratios over all games.
    """
    if path.is_file():
        print(f"Reporting end reason for file: {path}")
        print("End reason:", get_end_reason_from_file(path))

    elif path.is_dir():
        print(f"Reporting aggregate end reasons for directory: {path}")
        counts = {reason: 0 for reason in END_REASONS}
        game_count = 0
        for file in path.rglob("*"):
            if file.is_dir():
                assert file.name in ALLOWED_SUBDIRS, (f"The path under directory {path} is not a file: {file}, "
                                                      f"and does not correspond to an allowed subdirectory name")
                continue
            reason = get_end_reason_from_file(file)
            counts[reason] = counts.get(reason, 0) + 1
            game_count += 1

        print("Number of games:", game_count)
        for reason, count in counts.items():
            print(f"{reason.capitalize()}: {count} ({count / game_count:.2%})")

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: report_hint_intentions
# ---------------------------------------------------------------------------
def report_hint_intentions(path: Path) -> None:
    """
    Path must point to a JSON file or a directory of JSON files.
    Report the total hints given, total play-intention hints given and total
    discard-intention hints given.
    """
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = [
        file for file in path.rglob("*")
        if file.is_file() and file.suffix.lower() == ".json"
        ]
    else:
        raise ValueError(f"Path does not exist: {path}")
    
    if not files:
        print("No JSON game logs found.")
        return
    
    hint_play = 0
    hint_discards = 0
    game_count = 0

    for file in files:
        assert file.is_file() and file.suffix.lower() == ".json", (
            f"The path provided is not a JSON file: {file}"
        )

        with open(file, "r") as f:
            json_data = json.load(f)
            assert type(json_data) == dict, (
                f"Impossible to parse the JSON file into a dict: {file}"
            )

        game_count += 1
        for turn_entry in json_data["actions"]:
            for turn_data in turn_entry.values():
                if not isinstance(turn_data, dict):
                    continue

                action = turn_data.get("action", {})
                if not isinstance(action, dict):
                    continue

                if action.get("type") not in ("HINT_COLOR", "HINT_NUMBER"):
                    continue

                hint = action.get("hint", {})
                if not isinstance(hint, dict):
                    continue

                intention = hint.get("hint_intention")

                if intention == "Play":
                    hint_play += 1
                elif intention == "Discard":
                    hint_discards += 1

    total_hints = hint_play + hint_discards

    print("Games analyzed:", game_count)
    print("Total play-intention hints:", hint_play)
    print("Total discard-intention hints:", hint_discards)
    print("Total given hints:", total_hints)

    print("Average play-intention hints per game:",
      f"{hint_play / game_count}")
    print("Average discard-intention hints per game:",
      f"{hint_discards / game_count}")
    print("Average classified hints per game:",
      f"{total_hints / game_count}")


# ---------------------------------------------------------------------------
# Shared .txt log parsing (used by critical_misplays and critical_hints)
# ---------------------------------------------------------------------------
CARD_REGEX = re.compile(r"\b(white|red|blue|green|yellow) ([1-5])\b")
COLORS = ["green", "yellow", "white", "blue", "red"]
INITIAL_LIVES = 3
MAX_HINT_TOKENS = 8


def parse_card(text: str) -> Tuple[str, int]:
    """Return the first card (colour, rank) mentioned in text."""
    match = CARD_REGEX.search(text)
    assert match, f"Cannot parse a card from: {text}"
    return match.group(1), int(match.group(2))


def parse_game_states(path: Path) -> Tuple[int, List[dict]]:
    """
    Parse a .txt game log into the sequence of game states.
    - states[0] is the state before the first move
    - states[k] is the state right after move k
    Each state is a dict with keys:
    - "move": the move description, e.g. "Player 1 plays yellow 1 — and it failed" ("" for states[0])
    - "board": {colour: height}
    - "trash": list of (colour, rank)
    - "lives", "hints": lives and hint tokens left
    - "hands": {player number: list of (colour, rank)}
    Returns (number of players, states).
    """
    assert path.is_file(), f"The path provided is not a file: {path}"
    with open(path, "r") as f:
        lines = [line.rstrip("\n") for line in f]

    n_players = int(lines[0].split()[0])
    initial = {"move": "", "board": {col: 0 for col in COLORS}, "trash": [],
               "lives": INITIAL_LIVES, "hints": MAX_HINT_TOKENS, "hands": {}}
    states = [initial]
    current = None
    current_player = None
    in_starting_hands = False

    for line in lines:
        if line.startswith("Starting hands:"):
            in_starting_hands = True
        elif in_starting_hands and line.startswith("Player "):
            player, cards = line.split(":", 1)
            initial["hands"][int(player.split()[1])] = [parse_card(card) for card in cards.split(",")]
        elif line.startswith("Move "):
            in_starting_hands = False
            current = {"move": line.split(":", 1)[1].strip(), "hands": {}}
            states.append(current)
        elif current is None:
            continue
        elif line.startswith("Board:"):
            current["board"] = {col: int(height) for col, height in
                                re.findall(r"(green|yellow|white|blue|red) (\d+)", line)}
        elif line.startswith("Trash:"):
            current["trash"] = [(col, int(rank)) for col, rank in CARD_REGEX.findall(line)]
        elif line.startswith("Lives:"):
            lives, hints = re.fullmatch(r"Lives: (\d+) \| Hints: (\d+)", line.strip()).groups()
            current["lives"], current["hints"] = int(lives), int(hints)
        elif re.fullmatch(r"  Player \d+:", line):
            current_player = int(line.split()[1].rstrip(":"))
            current["hands"][current_player] = []
        elif re.match(r"    \[\d+\] ", line):
            current["hands"][current_player].append(parse_card(line.split("->")[0]))

    return n_players, states


def is_critical_card(card: Tuple[str, int], board: dict, trash: list) -> bool:
    """
    Whether the card is critical in the given state (taken before the card leaves the game):
    it is not played yet and every other copy of it is already in the trash.
    """
    col, rank = card
    return rank > board[col] and trash.count(card) == CARD_COUNTS[rank] - 1


def get_txt_log_files(path: Path) -> List[Path]:
    """Return [path] for a log file, or every .txt log under a directory of logs."""
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.txt"))
    raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: critical_misplays
# ---------------------------------------------------------------------------
def get_critical_misplay_info_from_file(path: Path) -> dict:
    """
    Get misplay information from a given .txt log file. Returns a dict with:
    - "misplays": number of misplays (lives lost)
    - "critical_misplays": list of (colour, rank) of the critical cards misplayed
    - "out_of_lives": whether the game ended because all lives were lost
    - "overall_loss": 25 - final score
    - "discard_loss", "misplay_loss", "combined_loss": estimated score loss from critical discards,
      from critical misplays, and from both (counted once when they block the same colour)
    """
    _, states = parse_game_states(path)
    misplays = 0
    critical_misplays = []
    for prev, state in zip(states, states[1:]):
        if "and it failed" not in state["move"]:
            continue
        misplays += 1
        card = parse_card(state["move"])
        if is_critical_card(card, prev["board"], prev["trash"]):
            critical_misplays.append(card)

    final_board = states[-1]["board"]
    critical_discards = [tuple(card) for card in get_critical_card_list_from_file(path)]
    return {
        "misplays": misplays,
        "critical_misplays": critical_misplays,
        "out_of_lives": states[-1]["lives"] == 0,
        "overall_loss": 25 - sum(final_board.values()),
        "discard_loss": estimate_blocked_score_loss(critical_discards, final_board),
        "misplay_loss": estimate_blocked_score_loss(critical_misplays, final_board),
        "combined_loss": estimate_blocked_score_loss(critical_discards + critical_misplays, final_board),
    }


def report_critical_misplays(path: Path) -> None:
    """
    Report stats on critical misplays and the score lost from them, next to the score lost from critical discards.
    If path points to a single log file, report the stats of the single game.
    If path points to a directory of log files, report aggregate stats over all games.
    """
    files = get_txt_log_files(path)
    if not files:
        print("No game logs found.")
        return
    print(f"Reporting critical misplays for: {path}")

    game_count = len(files)
    misplays = 0
    critical_by_rank = {rank: 0 for rank in CARD_COUNTS}
    games_with_critical_misplay = 0
    out_of_lives_games = 0
    out_of_lives_with_critical_misplay = 0
    losses = {"overall_loss": 0, "discard_loss": 0, "misplay_loss": 0, "combined_loss": 0}

    for file in files:
        info = get_critical_misplay_info_from_file(file)
        misplays += info["misplays"]
        for _, rank in info["critical_misplays"]:
            critical_by_rank[rank] += 1
        if info["critical_misplays"]:
            games_with_critical_misplay += 1
        if info["out_of_lives"]:
            out_of_lives_games += 1
            if info["critical_misplays"]:
                out_of_lives_with_critical_misplay += 1
        for key in losses:
            losses[key] += info[key]

    critical_misplays = sum(critical_by_rank.values())
    print("Games analyzed:", game_count)
    print("Total misplays (lives lost):", misplays)
    print("Critical misplays:", critical_misplays)
    if misplays > 0:
        print("Critical misplays ratio:", critical_misplays / misplays)
    print("Critical misplays by rank:", critical_by_rank)
    print("Games with at least one critical misplay:", games_with_critical_misplay)
    print("Games that ran out of lives:", out_of_lives_games,
          f"(with a critical misplay: {out_of_lives_with_critical_misplay})")
    print("Average misplays per game:", misplays / game_count)
    print("Average critical misplays per game:", critical_misplays / game_count)
    print("Average total score loss per game:", losses["overall_loss"] / game_count)
    print("Average estimated critical discard score loss per game:", losses["discard_loss"] / game_count)
    print("Average estimated critical misplay score loss per game:", losses["misplay_loss"] / game_count)
    print("Average estimated critical discard + misplay score loss per game:", losses["combined_loss"] / game_count)


# ---------------------------------------------------------------------------
# Command: critical_hints
# ---------------------------------------------------------------------------
def get_critical_hint_info_from_file(path: Path) -> List[dict]:
    """
    Get one dict per hint given in a .txt log file, with:
    - "tokens": the number of hint tokens available before the hint was given
    - "critical": whether the hint touched at least one critical card in the receiver's hand
    - "after": what each other player did right after the hint, before the hinter's next turn;
      after[0] is the next player's move, after[1] the move of the player after that, ...
      (n_players - 1 moves, fewer at the end of the game). Each is a dict with
      "discards", "critical_discards", "misplays" (0 or 1).
    """
    n_players, states = parse_game_states(path)
    hints = []
    for k in range(1, len(states)):
        match = re.fullmatch(r"Player \d+ hints Player (\d+): (.+)", states[k]["move"])
        if not match:
            continue
        receiver, hint = int(match.group(1)), match.group(2)
        prev = states[k - 1]
        number_hint = re.fullmatch(r"([1-5])s", hint)
        if number_hint:
            touched = [card for card in prev["hands"][receiver] if card[1] == int(number_hint.group(1))]
        else:
            touched = [card for card in prev["hands"][receiver] if card[0] == hint.split()[0]]

        info = {
            "tokens": prev["hints"],
            "critical": any(is_critical_card(card, prev["board"], prev["trash"]) for card in touched),
            "after": [],
        }
        for j in range(k + 1, min(k + n_players, len(states))):
            move, before = states[j]["move"], states[j - 1]
            discard = " discards " in move
            info["after"].append({
                "discards": int(discard),
                "critical_discards": int(discard and is_critical_card(parse_card(move), before["board"], before["trash"])),
                "misplays": int("and it failed" in move),
            })
        hints.append(info)
    return hints


def report_critical_hints(path: Path) -> None:
    """
    Report how many hints and critical-card hints were given at each number of available hint tokens,
    and what the other players did right after them (before the hinter's next turn).
    If path points to a single log file, report the stats of the single game.
    If path points to a directory of log files, report aggregate stats over all games.
    """
    files = get_txt_log_files(path)
    if not files:
        print("No game logs found.")
        return
    print(f"Reporting critical-card hints by hint tokens for: {path}")

    keys = ["discards", "critical_discards", "misplays"]
    # stats[tokens][critical]["count"] -> number of hints given with that many tokens
    # stats[tokens][critical]["after"][pos] -> totals over the move of the pos-th player after the hinter
    stats = {tokens: {critical: {"count": 0, "after": collections.defaultdict(lambda: dict.fromkeys(["moves"] + keys, 0))}
                      for critical in (True, False)}
             for tokens in range(1, MAX_HINT_TOKENS + 1)}
    for file in files:
        for hint in get_critical_hint_info_from_file(file):
            bucket = stats[hint["tokens"]][hint["critical"]]
            bucket["count"] += 1
            for pos, move in enumerate(hint["after"]):
                bucket["after"][pos]["moves"] += 1
                for key in keys:
                    bucket["after"][pos][key] += move[key]

    total_hints = sum(s[c]["count"] for s in stats.values() for c in (True, False))
    total_critical = sum(s[True]["count"] for s in stats.values())
    print("Games analyzed:", len(files))
    print("Total hints:", total_hints)
    print("Critical-card hints:", total_critical)
    if total_hints == 0:
        return

    print("\nHints by tokens available before the hint:")
    print(f"{'tokens':>6} | {'hints':>7} {'% of hints':>10} | {'critical':>8} {'% of crit':>9} | {'% critical':>10}")
    for tokens, s in stats.items():
        n_all = s[True]["count"] + s[False]["count"]
        n_crit = s[True]["count"]
        print(f"{tokens:>6} | {n_all:>7} {n_all / total_hints:>10.2%} | "
              f"{n_crit:>8} {n_crit / total_critical if total_critical else 0:>9.2%} | "
              f"{n_crit / n_all if n_all else 0:>10.2%}")

    positions = sorted({pos for s in stats.values() for c in (True, False) for pos in s[c]["after"]})
    for pos in positions:
        who = "Next player" if pos == 0 else f"Player {pos + 1} after the hinter"
        print(f"\n{who}'s move right after the hint, rate per move (critical hints vs other hints):")
        print(f"{'tokens':>6} | {'crit: disc':>10} {'crit disc':>9} {'misplay':>7} | "
              f"{'other: disc':>11} {'crit disc':>9} {'misplay':>7}")
        for tokens, s in stats.items():
            row = []
            for critical in (True, False):
                after = s[critical]["after"][pos]
                row.append([after[key] / after["moves"] if after["moves"] else 0 for key in keys])
            (c_disc, c_crit, c_mis), (o_disc, o_crit, o_mis) = row
            print(f"{tokens:>6} | {c_disc:>10.3f} {c_crit:>9.3f} {c_mis:>7.3f} | "
                  f"{o_disc:>11.3f} {o_crit:>9.3f} {o_mis:>7.3f}")


# ---------------------------------------------------------------------------
# Argument parser setup
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="log_analyzer",
        description=(
            "Parse and analyze log files using one of the provided commands. "
            "The input can be a path to a log file or a directory containing only log files, "
            "based on the appropriate command."
        ),
        epilog=(
            "Examples:\n"
            "  log_analyzer --help"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
        description="Available log analyzer commands",
    )

    # Critical discards command: report the stats on critical discards per game or per set of games
    critical_discards_parser = subparsers.add_parser(
        "critical_discards",
        help="Report stats on critical discards.",
        description="Report stats on critical discards.\n"
                    "If a path to a log file is passed as an argument, it will report stats on the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will report aggregate stats on the all games.",
    )
    critical_discards_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    critical_discards_parser.set_defaults(func=report_critical_discards)

    # Hint types command: report information on the types of hints provided (intentional vs redundant)
    hint_types_parser = subparsers.add_parser(
        "hint_types",
        help="Report details on the type of hints provided (intentional vs redundant).",
        description="Report details on the hints provided.\n"
                    "If a path to a JSON log file is passed as an argument, it will provide hint information the single game."
                    "If a path to a directory of JSON log files is passed as an argument,"
                    "it will report aggregate information on the all games.",
    )
    hint_types_parser.add_argument(
        "path",
        type=Path,
        help="Path to a JSON log file or directory of JSON log files.",
    )
    hint_types_parser.set_defaults(func=report_hint_types)

    # Third player hint command: analysis of the cases with a third player hint
    third_player_hints_parser = subparsers.add_parser(
        "third_player_hints",
        help="Analyze the effect of hinting the third player.",
        description="Report on the effect of hinting the third player. A 'third player hint' is defined as a hint that "
                    "Player A gives to Player C. Specifically, investigate the negative effects that these hints can "
                    "have on player B.\n"
                    "If a path to a log file is passed as an argument, it will analyze hint information the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will analyze aggregate information on the all games."
    )
    third_player_hints_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    third_player_hints_parser.set_defaults(func=report_third_player_hints)

    # Compare corresponding games command: compare two corresponding sets of logs by game number
    compare_corresponding_games_parser = subparsers.add_parser(
        "compare_corresponding_games",
        help="Compare corresponding games from two different trial runs.",
        description="Compare corresponding games from two different sets of games.\n"
                    "Each game from one run is compared directly with the game from another run with the same "
                    "run number. The comparison checks for the final score. Report how many games show a worse "
                    "performance in the new compared to the base.\n"
                    "Two paths must be provided for this command, and they must refer either both to log files or "
                    "both to directories of log files.\n"
                    "If two paths to log files are passed as an argument, the individual games will be compared.\n"
                    "If two paths to directories of log files are passed as an argument, corresponding games "
                    "will be compared."
    )
    compare_corresponding_games_parser.add_argument(
        "base_path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    compare_corresponding_games_parser.add_argument(
        "new_path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    compare_corresponding_games_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the list of games where the new does strictly better and strictly worse than the new.",
    )
    compare_corresponding_games_parser.set_defaults(func=compare_corresponding_games)

    # Lost lives command: report stats on lost lives during games
    lost_lives_parser = subparsers.add_parser(
        "lost_lives",
        help="Report stats on lost lives during games.",
        description="Report stats on the lives lost during the game\n"
                    "If a path to a log file is passed as an argument, it will report information on the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will report aggregate information on the all games."
    )
    lost_lives_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    lost_lives_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the list of games where all lives were exhausted.",
    )
    lost_lives_parser.set_defaults(func=report_lost_lives_info)

    # Potential score loss command: report the stats on total lost point overall and from critical discards
    potential_score_loss_parser = subparsers.add_parser(
        "report_potential_score_loss",
        help="Report stats on score loss due to critical discards.",
        description="Report stats on score loss from critical discards.\n"
                    "If a path to a log file is passed as an argument, it will report stats on the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will report aggregate stats on the all games.",
    )
    potential_score_loss_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.", )
    potential_score_loss_parser.set_defaults(func=report_potential_score_loss)

    # End reasons command: count how games ended (deck exhausted, out of lives, board completed)
    end_reasons_parser = subparsers.add_parser(
        "end_reasons",
        help="Count how games ended (deck exhausted, out of lives, board completed).",
        description="Report why games ended.\n"
                    "If a path to a log file is passed as an argument, it will report the end reason of the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will report counts and ratios over all games.",
    )
    end_reasons_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    end_reasons_parser.set_defaults(func=report_end_reasons)

    # hint intentions command: number of play and discard hints
    hint_intent_parser = subparsers.add_parser(
        "report_hint_intentions",
        help="Report stats on number of play and discard hints.",
        description="Report stats on number of play and discard intended hints.\n"
                            "If a path to a JSON file is passed as an argument, it will report stats on the single game."
                            "If a path to a directory of JSON files is passed as an argument,"
                            "it will report aggregate stats on the all games.",
        )
    hint_intent_parser.add_argument(
            "path", 
            type=Path, 
            help="Path to a JSON file or directory of JSON files.",) 
    hint_intent_parser.set_defaults(func=report_hint_intentions)

    # Critical misplays command: report stats on critical misplays and the score lost from them
    critical_misplays_parser = subparsers.add_parser(
        "critical_misplays",
        help="Report stats on critical misplays and the score loss from them.",
        description="Report stats on critical misplays and the estimated score loss from them, "
                    "next to the score loss from critical discards.\n"
                    "If a path to a log file is passed as an argument, it will report stats on the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will report aggregate stats on the all games.",
    )
    critical_misplays_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    critical_misplays_parser.set_defaults(func=report_critical_misplays)

    # Critical hints command: critical-card hints by number of hint tokens available
    critical_hints_parser = subparsers.add_parser(
        "critical_hints",
        help="Count critical-card hints at each number of available hint tokens.",
        description="Report how many hints and critical-card hints were given at each number of available "
                    "hint tokens, and what the other players did right after them.\n"
                    "If a path to a log file is passed as an argument, it will report stats on the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will report aggregate stats on the all games.",
    )
    critical_hints_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    critical_hints_parser.set_defaults(func=report_critical_hints)

    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    try:
        if args.command == "compare_corresponding_games":
            args.func(args.base_path, args.new_path, args.verbose)
        elif args.command == "lost_lives":
            args.func(args.path, args.verbose)
        else:
            args.func(args.path)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    main()