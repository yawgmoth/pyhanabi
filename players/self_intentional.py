import pdb
import random
from typing import override, Final
from unittest import result

from players import Player
from utils import (
    evaluate,
    get_possible,
    highest_playable_cards,
    playable,
    Action,
    discardable,
    Intent,
    Color,
    playable_v2,
    pretend,
    f,
    hint_color,
    hint_rank,
    format_intention,
    format_knowledge,
    pretend_discard,
    pretend_v1,
    pretend_v3,
    pretend_v6,
    pretend_v7,
    pretend_v9,
    pretend_v15,
    whattodo,
    MAX_HINT_TOKENS,
    COUNTS,
    TOTAL_CARDS,
    hint_weights_v8,
    pretend_v8,
    pretend_v10,
    life_cost_v17,
    play_utility_v17,
    discard_utility_v17,
    pretend_v19,
)

# V19: give_critical_hint only when at least this many hint tokens remain
V19_CRIT_HINT_MIN_TOKENS: Final[int] = 4

# V13: cost weights for hints to the subsequent player
V13_DELAY_COST: Final[float] = 0
V13_CRIT_PENALTY_WEIGHT: Final[float] = 3


class SelfIntentionalPlayer(Player):
    def __init__(self, name, pnr, version=0):
        super().__init__(name, pnr)
        self.got_hint = None
        self.hint_was_forced = False
        """V5: True iff the pending hint in got_hint was given while the giver
        held eight hint tokens, so it may have been forced (Section 6.7)."""
        self.valid_hints = []
        self.redun_hints = []
        self.crit_hints = []
        self.discard_crit = False
        self.risky_play = False
        self.version = version
        self.intent = None

        self._next_pnr: Final[int] = (self.pnr + 1) % 3
        """Player ID of the next player in 3P"""

        self._sub_pnr: Final[int] = (self.pnr + 2) % 3
        """Player ID of the subsequent player in 3P"""

    @override
    def reset(self) -> None:
        self.got_hint = None
        self.hint_was_forced = False
        self.valid_hints = []
        self.redun_hints = []
        self.crit_hints = []
        self.discard_crit = False
        self.risky_play = False
        self.intent = None
    def get_valid_hints(self):
        return self.valid_hints

    def get_redundant_hints(self):
        return self.redun_hints

    def get_critical_hints(self):
        return self.crit_hints

    def get_discard_crit(self):
        return self.discard_crit

    def get_risky_play(self):
        return self.risky_play

    def get_intent(self):
            return self.intent

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints, lives, deck_size
    ):
        num_players = len(knowledge)
        possible = []
        result = None
        ignore_dead = False
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - nr])))
        action = []
        self.valid_hints = []
        self.redun_hints = []
        self.crit_hints = []
        self.discard_crit = False
        self.risky_play = False
        self.intent = None

        if self.version == 0 or self.version == 11:
            if self.version == 11:
                ignore_dead = True
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result, ignore_dead)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)

                # give random hint
                else:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 1:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                # result = self.give_hint_v1(nr, hands, knowledge, trash, board, hints, num_players, result)
                if redundant_hints and not result:
                    result = self.give_redundant_hint(redundant_hints)

                result = self.give_hint_v1(nr, hands, knowledge, trash, board, hints, num_players, result)

                # give random hint
                if not result:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 2:
            # play a certainly playable card, or discard a certainly useless one
            result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # interpret received hint only if no safe action was found
            if self.got_hint:
                if not result:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                else:
                    self.got_hint = None

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # At max tokens cannot discard: redundant hint, else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_random_hint(valid_actions)

            # Fallback: discard the card with the lowest expected loss
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 3:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard
                result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
                # first, try to give a redundant hint
                if redundant_hints and not result:
                    result = self.give_redundant_hint(redundant_hints)

                # result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)

                # give random hint
                if not result:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 4:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)


            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # added this
            if deck_size < 16 and not result:
                result = self.play_v2(nr, knowledge, board, hints, possible, result, deck_size, lives)

            # added this
            if deck_size < 20 and not result:
                result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
                if not result and hints > 0:
                    result = self.give_best_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard
                #include reduncant hints in this algo
                result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
                # first, try to give a redundant hint
                #if redundant_hints and not result:
                 #   result = self.give_redundant_hint(redundant_hints)

                # result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)

                # give random hint
                if not result:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 5:

            # # SWAPPED
            #  # play or discard
            # if not result:
            #     result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # # Interpret recieved hint
            # if self.got_hint:
            #     result = self.received_hint(nr, knowledge, board, hints, result, action)


            # # give intentional hint
            # if not result:
            #     result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # # added this
            # if deck_size < 25 and lives > 1 and not result:
            #     result = self.play_v2(nr, knowledge, board, hints, possible, result, deck_size, lives)

            # # added this
            # if hints > 1 and not result:
            #     result = self.give_best_hint(nr, hands, knowledge, trash, board, hints, num_players, result)
            #     if not result and hints > 0:
            #         result = self.give_best_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # # give redundant hint
            # if hints == MAX_HINT_TOKENS and not result:
            #     # then I cannot discard
            #     #include reduncant hints in this algo
            #     result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
            #     # first, try to give a redundant hint
            #     #if redundant_hints and not result:
            #      #   result = self.give_redundant_hint(redundant_hints)

            #     # result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)

            #     # give random hint
            #     if not result:
            #         # if there are no redundant hints to give, give a random hint
            #         result = self.give_random_hint(valid_actions)

            # # discard
            # scores = self.discard_card(nr, knowledge, trash, board)

            # Interpret recieved hint, unless it may have been forced
            if self.got_hint:
                if self.hint_was_forced:
                    self.explanation.append(
                        ["Received hint may have been forced (giver held 8 "
                         "tokens): mental state updated, intention not interpreted"]
                    )
                    self.got_hint = None
                    self.hint_was_forced = False
                else:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                    self.hint_was_forced = False

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # forced to hint: give the informational rank hint of Section 6.7
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard
                result = self.give_forced_rank_hint(nr, hands, knowledge, board, num_players)
                if not result:
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 6:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint_v6(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)

                # give random hint
                else:
                # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 7:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)

                # give random hint
                else:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 8:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play a certainly playable card, or discard a certainly useless one
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint, scored with the V8 dynamic weights
            if not result:
                result, redundant_hints = self.give_intentional_hint_v8(
                    nr, hands, knowledge, trash, board, hints, num_players,
                    result, deck_size,
                )

            # At max tokens I cannot discard: redundant hint, else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_random_hint(valid_actions)

            # Fallback: discard the card with the lowest expected loss
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 13:
            # V13 (Player-Aware Hint): Same turn structure as version 0;
            # Only the intentional-hint scoring changes (Section 6.15).

            # Interpret received hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play a certainly playable card, or discard a certainly useless one
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint, with next-player-aware scoring
            if not result:
                result, redundant_hints = self.give_intentional_hint_v13(
                    nr, hands, knowledge, trash, board, hints, num_players, result
                )

            # At max tokens I cannot discard: redundant hint, else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_random_hint(valid_actions)

            # Fallback: discard the card with the lowest expected loss
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 9:
                    # Interpret recieved hint
                    if self.got_hint:
                        result = self.received_hint(nr, knowledge, board, hints, result, action)

                    # play or discard
                    if not result:
                        result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

                    # check if any other player may discard a critical card
                    discards_crit, crit_card_color, crit_card_rank, hintee_id = self.check_discard_critical_card(nr, knowledge, trash, board, num_players, hands)

                    # the other player might discard a critical card, give a hint to prevent that
                    if discards_crit and not result:
                        result = self.find_critical_card_hint(nr, hands, knowledge, trash, board, hints, num_players, crit_card_rank, crit_card_color, hintee_id, result)

                    # give intentional hint
                    if not result:
                        result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

                    if not result:
                        result = self.give_critical_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

                    # give redundant hint
                    if hints == MAX_HINT_TOKENS and not result:
                        # then I cannot discard

                        # first, try to give a redundant hint
                        if redundant_hints:
                            result = self.give_redundant_hint(redundant_hints)

                        # give random hint
                        else:
                            # if there are no redundant hints to give, give a random hint
                            result = self.give_random_hint(valid_actions)

                    # discard
                    scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 10:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play a certainly playable card, or discard a certainly useless one
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint, scored with V10 remaining-lives-weighted play
            if not result:
                result, redundant_hints = self.give_intentional_hint_v10(
                    nr, hands, knowledge, trash, board, hints, num_players,
                    result, deck_size, lives,
                )

            # At max tokens I cannot discard: redundant hint, else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_random_hint(valid_actions)

            # Fallback: discard the card with the lowest expected loss
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 14:
            # V14 = V5 + V8: V8's dynamic-weight intentional hinting, plus
            # V5's handling of hints given while the giver held 8 tokens
            # (i.e. the giver was forced to hint, so the hint may not be
            # intentional). Observed V8 bad games were misfires caused by a
            # preceding random forced hint being misread as intentional.

            # Interpret recieved hint, unless it may have been forced (V5)
            if self.got_hint:
                if self.hint_was_forced:
                    self.explanation.append(
                        ["Received hint may have been forced (giver held 8 "
                         "tokens): mental state updated, intention not interpreted"]
                    )
                    self.got_hint = None
                    self.hint_was_forced = False
                else:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                    self.hint_was_forced = False

            # play a certainly playable card, or discard a certainly useless one
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint, scored with the V8 dynamic weights
            if not result:
                result, redundant_hints = self.give_intentional_hint_v8(
                    nr, hands, knowledge, trash, board, hints, num_players,
                    result, deck_size,
                )

            # At max tokens I cannot discard. Prefer a redundant hint (V8);
            # otherwise give the forced rank hint of Section 6.7 (V5), which
            # avoids suggesting a play, instead of a fully random hint.
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_forced_rank_hint(nr, hands, knowledge, board, num_players)
                    if not result:
                        result = self.give_random_hint(valid_actions)

            # Fallback: discard the card with the lowest expected loss
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 15:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)


            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)


            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint_v15(nr, hands, knowledge, trash, board, hints, num_players, result, ignore_dead)


            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard


                # first, try to give a redundant hint
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)


                # give random hint
                else:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)


            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 18:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # check if any other player may discard a critical card
            discards_crit, crit_card_color, crit_card_rank, hintee_id = self.check_discard_critical_card(nr, knowledge, trash, board, num_players, hands)

            # the other player might discard a critical card, give a hint to prevent that
            if discards_crit and not result:
                result = self.find_critical_card_hint(nr, hands, knowledge, trash, board, hints, num_players, crit_card_rank, crit_card_color, hintee_id, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint_v6(nr, hands, knowledge, trash, board, hints, num_players, result)

            if not result:
                result = self.give_critical_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)

                # give random hint
                else:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)


        if self.version == 17:
            # V17 = V14 + lives-aware risky play: before the fallback
            # discard, play the most promising card instead if its estimated
            # utility beats discarding V14's discard candidate.

            # Interpret recieved hint, unless it may have been forced (V5)
            if self.got_hint:
                if self.hint_was_forced:
                    self.explanation.append(
                        ["Received hint may have been forced (giver held 8 "
                         "tokens): mental state updated, intention not interpreted"]
                    )
                    self.got_hint = None
                    self.hint_was_forced = False
                else:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                    self.hint_was_forced = False

            # play a certainly playable card, or discard a certainly useless one
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint, scored with the V8 dynamic weights
            if not result:
                result, redundant_hints = self.give_intentional_hint_v8(
                    nr, hands, knowledge, trash, board, hints, num_players,
                    result, deck_size,
                )

            # At max tokens I cannot discard: redundant hint, else forced
            # rank hint (V5), else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_forced_rank_hint(nr, hands, knowledge, board, num_players)
                    if not result:
                        result = self.give_random_hint(valid_actions)

            # V14's discard candidate
            scores = self.discard_card(nr, knowledge, trash, board)

            # Risky play instead of the fallback discard
            if not result:
                result = self.risky_play_v17(
                    nr, knowledge, board, hints, lives, deck_size, num_players,
                    scores[0][0],
                )

        if self.version == 19:
            # V19 = V17 + V18: V14's forced-hint handling and risky play
            # (V17), V18's critical-card protection, and intentional hints
            # scored with V8's dynamic weights while preferring play hints (V6).
            redundant_hints = []

            # Interpret recieved hint, unless it may have been forced (V5)
            if self.got_hint:
                if self.hint_was_forced:
                    self.explanation.append(
                        ["Received hint may have been forced (giver held 8 "
                         "tokens): mental state updated, intention not interpreted"]
                    )
                    self.got_hint = None
                    self.hint_was_forced = False
                else:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                    self.hint_was_forced = False

            # play a certainly playable card, or discard a certainly useless one
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # check if any other player may discard a critical card (V18)
            discards_crit, crit_card_color, crit_card_rank, hintee_id = self.check_discard_critical_card(nr, knowledge, trash, board, num_players, hands)

            # the other player might discard a critical card, give a hint to prevent that
            if discards_crit and not result:
                result = self.find_critical_card_hint(nr, hands, knowledge, trash, board, hints, num_players, crit_card_rank, crit_card_color, hintee_id, result)
                if result:
                    self.intent = "Save"

            # give intentional hint, V8 weights + V6 play-hint preference
            if not result:
                result, redundant_hints = self.give_intentional_hint_v19(
                    nr, hands, knowledge, trash, board, hints, num_players,
                    result, deck_size,
                )

            # At max tokens I cannot discard: redundant hint, else forced
            # rank hint (V5), else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_forced_rank_hint(nr, hands, knowledge, board, num_players)
                    if not result:
                        result = self.give_random_hint(valid_actions)

            # V14's discard candidate
            scores = self.discard_card(nr, knowledge, trash, board)

            # Risky play instead of the fallback discard (V17)
            if not result:
                result = self.risky_play_v17(
                    nr, knowledge, board, hints, lives, deck_size, num_players,
                    scores[0][0],
                )

            # hint any critical card, only when tokens are plentiful (V18)
            if not result and hints >= V19_CRIT_HINT_MIN_TOKENS:
                result = self.give_critical_hint(nr, hands, knowledge, trash, board, hints, num_players, result)
                if result:
                    self.intent = "Save"

        if self.version == 20:
            # V20 = V0 + lives-aware risky play (V17): isolates the effect of
            # risky play, without V14's forced-hint handling (V5) or dynamic
            # hint weights (V8).

            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result, ignore_dead)

            # At max tokens I cannot discard: redundant hint, else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_random_hint(valid_actions)

            # V0's discard candidate
            scores = self.discard_card(nr, knowledge, trash, board)

            # Risky play instead of the fallback discard (V17)
            if not result:
                result = self.risky_play_v17(
                    nr, knowledge, board, hints, lives, deck_size, num_players,
                    scores[0][0],
                )

        if result:
            assert result in valid_actions
            return result
        assert scores[0][0] in valid_actions
        return scores[0][0]

    def give_redundant_hint(self, redundant_hints):
        selected_action, hintee_id = random.choice(redundant_hints)
        if selected_action[0] is Action.ActionType.HINT_COLOR:
            result = Action(
                            Action.ActionType.HINT_COLOR,
                            pnr=hintee_id,
                            col=Color(selected_action[1]),
                        )
        else:
            result = Action(
                            Action.ActionType.HINT_NUMBER,
                            pnr=hintee_id,
                            num=selected_action[1],
                        )
        return result

    def find_critical_card_hint(self, nr, hands, knowledge, trash, board, hints, num_players, rank, colour, hintee_id, result):
        """
        Find the highest-scoring intentional hint identifying the critical card
        with colour and rank for player hintee_id, otherwise the highest-scoring
        hint identifying the critical card with colour and rank that does not
        cause misplaying or discarding the critical card.
        """
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []

            if num_players == 2 or hintee_id == self._next_pnr:
                hintee_intentions = intents_for_next
            else:
                assert intents_for_sub is not None
                hintee_intentions = intents_for_sub

            hint_action = (Action.ActionType.HINT_COLOR, colour)
            isvalid, score, expl = pretend(
                hint_action,
                knowledge[hintee_id],
                hintee_intentions,
                hands[hintee_id],
                board,
                trash,
            )
            self.explanation.append(
                ["Prediction for: Hint Color " + colour.display_name]
                + list(map(format_intention, expl))
            )
            if isvalid:
                valid.append((hint_action, score, hintee_id))
                if hint_action[0] == Action.ActionType.HINT_NUMBER:
                    self.crit_hints.append((hint_action[1], hintee_id, score))
                else:
                    self.crit_hints.append((hint_action[1].display_name, hintee_id, score))


            hint_action = (Action.ActionType.HINT_NUMBER, rank)
            isvalid, score, expl = pretend(
                hint_action,
                knowledge[hintee_id],
                hintee_intentions,
                hands[hintee_id],
                board,
                trash,
            )
            self.explanation.append(
                ["Prediction for: Hint Number " + str(rank)]
                + list(map(format_intention, expl))
            )
            if isvalid:
                valid.append((hint_action, score, hintee_id))
                if hint_action[0] == Action.ActionType.HINT_NUMBER:
                    self.crit_hints.append((hint_action[1], hintee_id, score))
                else:
                    self.crit_hints.append((hint_action[1].display_name, hintee_id, score))
            if not valid and not result:
                hint_action = (Action.ActionType.HINT_COLOR, colour)
                (isvalid, score, expl) = pretend_v9(
                                            hint_action,
                                            knowledge[hintee_id],
                                            hintee_intentions,
                                            hands[hintee_id],
                                            board,
                                            trash
                                        )
                if isvalid:
                    valid.append((hint_action, score, hintee_id))
                    if hint_action[0] == Action.ActionType.HINT_NUMBER:
                        self.crit_hints.append((hint_action[1], hintee_id, score))
                    else:
                        self.crit_hints.append((hint_action[1].display_name, hintee_id, score))
                hint_action = (Action.ActionType.HINT_NUMBER, rank)
                (isvalid, score, expl) = pretend_v9(
                    hint_action,
                    knowledge[hintee_id],
                    hintee_intentions,
                    hands[hintee_id],
                    board,
                    trash
                )
                if isvalid:
                    valid.append((hint_action, score, hintee_id))
                    if hint_action[0] == Action.ActionType.HINT_NUMBER:
                        self.crit_hints.append((hint_action[1], hintee_id, score))
                    else:
                        self.crit_hints.append((hint_action[1].display_name, hintee_id, score))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result


    def check_discard_critical_card(self, nr, knowledge, trash, board, num_players, hands):
        for hintee_id in range(num_players):
            if hintee_id == nr:
                continue
            else:
                scores = self.discard_card(hintee_id, knowledge, trash, board)
                action = scores[0][0]
                #col = action.col
                #rank = action.num
                if action.cnr >= len(hands[hintee_id]):
                    continue 
                card = hands[hintee_id][action.cnr]
                col = card[0]
                rank = card[1]
                 # check if the card is critical
                count = 0
                for card in trash:
                    if card[0] == col and card[1] == rank:
                        count += 1

                if rank == 5 or ((rank == 2 or rank == 3 or rank == 4) and count == 1) or (rank == 1 and count == 2):
                    self.discard_crit = True
                    return True, col, rank, hintee_id


        return False, None, None, None


    def discard_card(self, nr, knowledge, trash, board):
        self.explanation.append(
            ["My Knowledge"] + list(map(format_knowledge, knowledge[nr]))
        )
        possible = [
            Action(Action.ActionType.DISCARD, cnr=i) for i in range(self._hand_size)
        ]

        scores = list(
            map(lambda p: pretend_discard(p, knowledge[nr], board, trash), possible)
        )

        def format_term(x):
            (col, rank, _, prob, val) = x
            return (
                col.display_name
                + " "
                + str(rank)
                + " ({:.2f}%): {:.2f}".format(prob * 100, val)
            )

        self.explanation.append(
            ["Discard Scores"]
            + list(
                map(
                    lambda x: "\n".join(map(format_term, x[2])) + "\n%.2f" % (x[1]),
                    scores,
                )
            )
        )
        scores.sort(key=lambda x: -x[1])
        return scores

    def risky_play_v17(
        self, nr, knowledge, board, hints, lives, deck_size, num_players, discard_action
    ):
        """
        V17: return a PLAY action if playing some card beats discarding
        discard_action (V14's discard candidate), else None so that the
        caller falls back to that discard.

        Q_play(i)    = p_i - sum_{x unplayable} P_i(x) l(x) - (1 - p_i) C(L, T)
        Q_discard(j) = -sum_x P_j(x) l(x) + V_token(hints)
        with C(L, T) = alpha * T / (L - 1) and T = deck_size + num_players
        (one turn per card left, plus the final round).
        """
        # Losing the last life ends the game: never risk it
        if lives <= 1:
            return None

        turns_left = deck_size + num_players
        life_cost = life_cost_v17(lives, turns_left)
        q_discard = discard_utility_v17(knowledge[nr][discard_action.cnr], board, hints)

        best = None  # (q_play, p, card index)
        for i, k in enumerate(knowledge[nr]):
            q_play, p = play_utility_v17(k, board, life_cost)
            if best is None or q_play > best[0]:
                best = (q_play, p, i)

        q_play, p, cnr = best
        self.explanation.append(
            [
                "V17 risky play",
                "Lives: {} | Turns left: {} | Life cost: {:.2f}".format(lives, turns_left, life_cost),
                "Best play: card {} (p = {:.2f}, Q = {:.2f})".format(cnr, p, q_play),
                "Discard: card {} (Q = {:.2f})".format(discard_action.cnr, q_discard),
            ]
        )

        # Ties keep V14's discard
        if q_play > q_discard:
            self.risky_play = True
            return Action(Action.ActionType.PLAY, cnr=cnr)
        return None

    def give_random_hint(self, valid_actions):
        result = random.choice(
                    [
                        action
                        for action in valid_actions
                        if action.action_type
                        in {Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER}
                    ]
                )

        return result

    def give_forced_rank_hint(self, nr, hands, knowledge, board, num_players):
        """V5: choose the forced rank hint of Section 6.7.

        Among every legal rank hint (one per rank present in each partner's
        hand), prefer a rank that no firework is currently awaiting, so that
        the hint does not suggest a play. Among the preferred hints, give the
        one that removes the most identities from the recipient's mental
        state; if every rank in every hand is awaited by some firework, give
        whichever rank hint removes the most identities.

        Returns the chosen hint as an Action, or None if no partner holds any
        card (which cannot happen in a running game).
        """
        # the rank each unfinished firework is awaiting: one above its top
        awaited_ranks = {board[c][1] + 1 for c in Color if board[c][1] < 5}

        # candidate tuples: (preferred, identities removed, hintee, rank)
        candidates: list[tuple[bool, int, int, int]] = []

        for hintee_id in range(num_players):
            if hintee_id == nr:
                continue

            # a rank hint is only legal for ranks the hintee actually holds
            for r in sorted({num for (_, num) in hands[hintee_id]}):
                removed = self._identities_removed_by_rank_hint(
                    hands[hintee_id], knowledge[hintee_id], r
                )
                preferred = r not in awaited_ranks
                candidates.append((preferred, removed, hintee_id, r))
                self.explanation.append(
                    [
                        "Forced rank hint candidate",
                        "Rank " + str(r) + " to player " + str(hintee_id),
                        "not awaited" if preferred else "awaited by a firework",
                        "removes " + str(removed) + " identities",
                    ]
                )

        if not candidates:
            return None

        # Sorting on (preferred, removed) descending implements the two-level
        # preference: any non-awaited rank beats any awaited one, and ties
        # are broken by the number of identities removed. The sort is stable,
        # so remaining ties keep hand order (next player first, lowest rank
        # first), which keeps the choice deterministic.
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        _, _, hintee_id, rank = candidates[0]

        return Action(Action.ActionType.HINT_NUMBER, pnr=hintee_id, num=rank)

    def _identities_removed_by_rank_hint(self, hand, hand_knowledge, rank):
        """V5: count the identities a rank hint removes from a hand's mental
        state.

        The count covers every card in the hand, not only the cards the hint
        positively identifies: for an identified card (its true rank equals
        rank) every still-possible identity of a *different* rank is removed,
        while for every other card the identities of rank rank are removed.
        An identity counts as removed when its cell goes from a positive
        count to zero.
        """
        removed = 0
        for (_, num), k in zip(hand, hand_knowledge):
            if num == rank:
                # positively identified: all other ranks are ruled out
                for c in Color:
                    for i in range(len(COUNTS)):
                        if i + 1 != rank and k[c][i] > 0:
                            removed += 1
            else:
                # not identified: the hinted rank is ruled out for this card
                for c in Color:
                    if k[c][rank - 1] > 0:
                        removed += 1
        return removed

    def _giver_hint_tokens(self, game):
        """V5: return the number of hint tokens the giver held *when giving*
        the hint that inform() is currently processing.

        The two engines expose this differently:
        - HanasimGame calls inform() after advancing its observation, so
          game._obs.hint_tokens is the post-hint count and the hint has
          already spent one token: add it back.
        - The legacy Game calls inform() before deducting the token, so
          game.hints is already the pre-hint count.
        """
        obs = getattr(game, "_obs", None)
        if obs is not None:
            return min(obs.hint_tokens + 1, MAX_HINT_TOKENS)
        return game.hints

    def give_best_hint(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    isvalid, score, expl = evaluate(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))


                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    isvalid, score, expl = evaluate(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Number " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result
    def give_critical_hint(self, nr, hands, knowledge, trash, board, hints, num_players, result):

        if num_players == 2:
                    intents_for_next = self._create_intents(
                        hands[(self.pnr + 1) % 2], board, trash
                    )
                    self.explanation.append(
                        ["Intentions for next player"]
                        + list(map(format_intention, intents_for_next))
                    )
                    intents_for_sub = None
        else:
                    intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
                    self.explanation.append(
                        ["Intentions for next player"]
                        + list(map(format_intention, intents_for_next))
                    )

                    intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
                    self.explanation.append(
                        ["Intentions for subsequent player"]
                        + list(map(format_intention, intents_for_sub))
                    )

        if hints > 0:
                    hint_action: tuple[Action.ActionType, Color | int]
                    valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
                    redundant_hints: list[
                        tuple[tuple[Action.ActionType, Color | int], int]
                    ] = []

                    for hintee_id in range(num_players):
                        if hintee_id == nr:
                            continue
                        elif num_players == 2 or hintee_id == self._next_pnr:
                            hintee_intentions = intents_for_next
                        else:
                            assert intents_for_sub is not None
                            hintee_intentions = intents_for_sub

                    valid = []
                    for hintee_id in range(num_players):
                        if hintee_id == nr:
                            continue
                        elif num_players == 2 or hintee_id == self._next_pnr:
                            hintee_intentions = intents_for_next
                        else:
                            assert intents_for_sub is not None
                            hintee_intentions = intents_for_sub

                        for (col, num) in hands[hintee_id]:
                                count = 0
                                for card in trash:
                                    if card[0] == col and card[1] == num:
                                        count += 1
                                if num == 5 or ((num == 2 or num == 3 or num == 4) and count == 1) or (num == 1 and count == 2):
                                    hint_action = (Action.ActionType.HINT_COLOR, col)
                                    (isvalid, score, expl) = pretend_v9(
                                                                hint_action,
                                                                knowledge[hintee_id],
                                                                hintee_intentions,
                                                                hands[hintee_id],
                                                                board,
                                                                trash
                                                            )
                                    if isvalid:
                                        valid.append((hint_action, score, hintee_id))
                                    hint_action = (Action.ActionType.HINT_NUMBER, num)
                                    (isvalid, score, expl) = pretend_v9(
                                        hint_action,
                                        knowledge[hintee_id],
                                        hintee_intentions,
                                        hands[hintee_id],
                                        board,
                                        trash
                                    )
                                    if isvalid:
                                        valid.append((hint_action, score, hintee_id))

                    if valid and not result:
                                    # sort descending by hint score
                                    valid.sort(key=lambda x: x[1], reverse=True)

                                    selected_action, _, hintee_id = valid[0]
                                    if selected_action[0] is Action.ActionType.HINT_COLOR:
                                        result = Action(
                                            Action.ActionType.HINT_COLOR,
                                            pnr=hintee_id,
                                            col=Color(selected_action[1]),
                                        )
                                    else:
                                        result = Action(
                                            Action.ActionType.HINT_NUMBER,
                                            pnr=hintee_id,
                                            num=selected_action[1],
                                        )

        return result


    def give_intentional_hint(self, nr, hands, knowledge, trash, board, hints, num_players, result, ignore_dead=False):
        redundant_hints = []
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    if self.version == 7:
                        (isvalid, score, expl) = pretend_v7(
                            hint_action,
                            knowledge[hintee_id],
                            hintee_intentions,
                            hands[hintee_id],
                            board,
                            trash
                        )
                    else:
                        (isvalid, score, expl) = pretend(
                            hint_action,
                            knowledge[hintee_id],
                            hintee_intentions,
                            hands[hintee_id],
                            board,
                            trash,
                            ignore_dead
                        )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.valid_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.redun_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.redun_hints.append((hint_action[1].display_name, hintee_id, score))

                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    if self.version == 7:
                        (isvalid, score, expl) = pretend_v7(
                            hint_action,
                            knowledge[hintee_id],
                            hintee_intentions,
                            hands[hintee_id],
                            board,
                            trash
                        )
                    else:
                        (isvalid, score, expl) = pretend(
                            hint_action,
                            knowledge[hintee_id],
                            hintee_intentions,
                            hands[hintee_id],
                            board,
                            trash,
                            ignore_dead
                        )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.valid_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.redun_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.redun_hints.append((hint_action[1].display_name, hintee_id, score))


            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result, redundant_hints

    def give_intentional_hint_v15(self, nr, hands, knowledge, trash, board, hints, num_players, result, ignore_dead=False):
            redundant_hints = []
            if num_players == 2:
                intents_for_next = self._create_intents(
                    hands[(self.pnr + 1) % 2], board, trash
                )
                self.explanation.append(
                    ["Intentions for next player"]
                    + list(map(format_intention, intents_for_next))
                )
                intents_for_sub = None
            else:
                intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
                self.explanation.append(
                    ["Intentions for next player"]
                    + list(map(format_intention, intents_for_next))
                )
   
                intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
                self.explanation.append(
                    ["Intentions for subsequent player"]
                    + list(map(format_intention, intents_for_sub))
                )
   
            if hints > 0:
                hint_action: tuple[Action.ActionType, Color | int]
                valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
                redundant_hints: list[
                    tuple[tuple[Action.ActionType, Color | int], int]
                ] = []
   
                for hintee_id in range(num_players):
                    if hintee_id == nr:
                        continue
                    elif num_players == 2 or hintee_id == self._next_pnr:
                        hintee_intentions = intents_for_next
                    else:
                        assert intents_for_sub is not None
                        hintee_intentions = intents_for_sub
   
                    for c in Color:
                        hint_action = (Action.ActionType.HINT_COLOR, c)
                        if self.version == 7:
                            (isvalid, score, expl) = pretend_v7(
                                hint_action,
                                knowledge[hintee_id],
                                hintee_intentions,
                                hands[hintee_id],
                                board,
                                trash
                            )
                        else:
                            (isvalid, score, expl) = pretend_v15(
                                hint_action,
                                knowledge[hintee_id],
                                hintee_intentions,
                                hands[hintee_id],
                                board,
                                trash,
                                hints,
                                ignore_dead
                            )
                        self.explanation.append(
                            ["Prediction for: Hint Color " + c.display_name]
                            + list(map(format_intention, expl))
                        )
                        if isvalid:
                            valid.append((hint_action, score, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.valid_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                        if expl == ["No new information"]:
                            redundant_hints.append((hint_action, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.redun_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.redun_hints.append((hint_action[1].display_name, hintee_id, score))
   
                    for r in range(5):
                        r += 1
                        hint_action = (Action.ActionType.HINT_NUMBER, r)
                        if self.version == 7:
                            (isvalid, score, expl) = pretend_v7(
                                hint_action,
                                knowledge[hintee_id],
                                hintee_intentions,
                                hands[hintee_id],
                                board,
                                trash
                            )
                        else:
                            (isvalid, score, expl) = pretend_v15(
                                hint_action,
                                knowledge[hintee_id],
                                hintee_intentions,
                                hands[hintee_id],
                                board,
                                trash,
                                hints,
                                ignore_dead
                            )
                        self.explanation.append(
                            ["Prediction for: Hint Rank " + str(r)]
                            + list(map(format_intention, expl))
                        )
                        if isvalid:
                            valid.append((hint_action, score, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.valid_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                        if expl == ["No new information"]:
                            redundant_hints.append((hint_action, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.redun_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.redun_hints.append((hint_action[1].display_name, hintee_id, score))
   
   
                if valid and not result:
                    # sort descending by hint score
                    valid.sort(key=lambda x: x[1], reverse=True)
   
                    selected_action, _, hintee_id = valid[0]
                    if selected_action[0] is Action.ActionType.HINT_COLOR:
                        result = Action(
                            Action.ActionType.HINT_COLOR,
                            pnr=hintee_id,
                            col=Color(selected_action[1]),
                        )
                    else:
                        result = Action(
                            Action.ActionType.HINT_NUMBER,
                            pnr=hintee_id,
                            num=selected_action[1],
                        )
   
            return result, redundant_hints

    
    def give_intentional_hint_v6(self, nr, hands, knowledge, trash, board, hints, num_players, result):
            redundant_hints = []
            play_hints = []
            discard_hints = []
            if num_players == 2:
                intents_for_next = self._create_intents(
                    hands[(self.pnr + 1) % 2], board, trash
                )
                self.explanation.append(
                    ["Intentions for next player"]
                    + list(map(format_intention, intents_for_next))
                )
                intents_for_sub = None
            else:
                intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
                self.explanation.append(
                    ["Intentions for next player"]
                    + list(map(format_intention, intents_for_next))
                )

                intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
                self.explanation.append(
                    ["Intentions for subsequent player"]
                    + list(map(format_intention, intents_for_sub))
                )

            if hints > 0:
                hint_action: tuple[Action.ActionType, Color | int]
                valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
                redundant_hints: list[
                    tuple[tuple[Action.ActionType, Color | int], int]
                ] = []

                for hintee_id in range(num_players):
                    if hintee_id == nr:
                        continue
                    elif num_players == 2 or hintee_id == self._next_pnr:
                        hintee_intentions = intents_for_next
                    else:
                        assert intents_for_sub is not None
                        hintee_intentions = intents_for_sub

                    for c in Color:
                        hint_action = (Action.ActionType.HINT_COLOR, c)
                        (isvalid, score, expl, isplay) = pretend_v6(
                            hint_action,
                            knowledge[hintee_id],
                            hintee_intentions,
                            hands[hintee_id],
                            board,
                            trash
                        )
                        self.explanation.append(
                            ["Prediction for: Hint Color " + c.display_name]
                            + list(map(format_intention, expl))
                        )
                        if isvalid:
                            valid.append((hint_action, score, hintee_id))
                            if isplay:
                                play_hints.append((hint_action, score, hintee_id))
                            else:
                                discard_hints.append((hint_action, score, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.valid_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                        if expl == ["No new information"]:
                            redundant_hints.append((hint_action, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.redun_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.redun_hints.append((hint_action[1].display_name, hintee_id, score))

                    for r in range(5):
                        r += 1
                        hint_action = (Action.ActionType.HINT_NUMBER, r)
                        (isvalid, score, expl, isplay) = pretend_v6(
                            hint_action,
                            knowledge[hintee_id],
                            hintee_intentions,
                            hands[hintee_id],
                            board,
                            trash
                        )
                        self.explanation.append(
                            ["Prediction for: Hint Rank " + str(r)]
                            + list(map(format_intention, expl))
                        )
                        if isvalid:
                            valid.append((hint_action, score, hintee_id))
                            if isplay:
                                play_hints.append((hint_action, score, hintee_id))
                            else:
                                discard_hints.append((hint_action, score, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.valid_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                        if expl == ["No new information"]:
                            redundant_hints.append((hint_action, hintee_id))
                            if hint_action[0] == Action.ActionType.HINT_NUMBER:
                                self.redun_hints.append((hint_action[1], hintee_id, score))
                            else:
                                self.redun_hints.append((hint_action[1].display_name, hintee_id, score))


                if valid and not result:
                    # sort descending by hint score
                    self.intent = "Discard"
                    if hints <= 0 and discard_hints:
                        valid = discard_hints
                    elif play_hints:
                        valid = play_hints
                        self.intent = "Play"

                    valid.sort(key=lambda x: x[1], reverse=True)

                    selected_action, _, hintee_id = valid[0]
                    if selected_action[0] is Action.ActionType.HINT_COLOR:
                        result = Action(
                            Action.ActionType.HINT_COLOR,
                            pnr=hintee_id,
                            col=Color(selected_action[1]),
                        )
                    else:
                        result = Action(
                            Action.ActionType.HINT_NUMBER,
                            pnr=hintee_id,
                            num=selected_action[1],
                        )
            if not result:
                self.intent = None
            return result, redundant_hints

    def give_intentional_hint_v8(
        self, nr, hands, knowledge, trash, board, hints, num_players, result, deck_size
    ):
        """
        V7: give_intentional_hint() with state-dependent hint scoring.
        Return (result, redundant_hints), like give_intentional_hint().
        """
        redundant_hints = []

        # --- Step 1: assign an intent to each card in each partner's hand ---
        # (identical to give_intentional_hint)
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            # --- Step 2: compute the dynamic weights for this turn ----------
            # The draw pile starts at TOTAL_CARDS minus the dealt cards.
            initial_draw_pile = TOTAL_CARDS - num_players * self._hand_size
            weights = hint_weights_v8(hints, deck_size, initial_draw_pile)
            self.explanation.append(
                [
                    "V7 hint weights",
                    "Play: {:.2f}".format(weights[0]),
                    "Discard: {:.2f}".format(weights[1]),
                    "May Discard: {:.2f}".format(weights[2]),
                ]
            )

            # --- Step 3: enumerate and score every legal hint ---------------
            hint_action: tuple[Action.ActionType, Color | int]
            # scores are floats under V7 (dynamic weights), hence the type
            valid: list[tuple[tuple[Action.ActionType, Color | int], float, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                # every color hint for this partner
                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend_v8(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                        weights,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        self.valid_hints.append(
                            (hint_action[1].display_name, hintee_id, score)
                        )
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        self.redun_hints.append(
                            (hint_action[1].display_name, hintee_id, score)
                        )

                # every rank hint for this partner
                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend_v8(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                        weights,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        self.valid_hints.append((hint_action[1], hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        self.redun_hints.append((hint_action[1], hintee_id, score))

            # --- Step 4: give the highest-scoring valid hint ----------------
            # (identical to give_intentional_hint; ties keep enumeration
            # order because Python's sort is stable)
            if valid and not result:
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result, redundant_hints

    def give_intentional_hint_v19(
        self, nr, hands, knowledge, trash, board, hints, num_players, result, deck_size
    ):
        """
        V19: give_intentional_hint_v8() scored with pretend_v19, preferring
        hints that make the hintee play (V6). Sets self.intent.
        Return (result, redundant_hints), like give_intentional_hint().
        """
        redundant_hints = []
        play_hints = []

        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            initial_draw_pile = TOTAL_CARDS - num_players * self._hand_size
            weights = hint_weights_v8(hints, deck_size, initial_draw_pile)
            self.explanation.append(
                [
                    "V19 hint weights",
                    "Play: {:.2f}".format(weights[0]),
                    "Discard: {:.2f}".format(weights[1]),
                    "May Discard: {:.2f}".format(weights[2]),
                ]
            )

            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], float, int]] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                # every color hint, then every rank hint, for this partner
                candidates = [(Action.ActionType.HINT_COLOR, c) for c in Color]
                candidates += [(Action.ActionType.HINT_NUMBER, r) for r in range(1, 6)]
                for hint_action in candidates:
                    (isvalid, score, expl, isplay) = pretend_v19(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                        weights,
                    )
                    if hint_action[0] == Action.ActionType.HINT_COLOR:
                        label = hint_action[1].display_name
                        self.explanation.append(
                            ["Prediction for: Hint Color " + label]
                            + list(map(format_intention, expl))
                        )
                    else:
                        label = hint_action[1]
                        self.explanation.append(
                            ["Prediction for: Hint Rank " + str(label)]
                            + list(map(format_intention, expl))
                        )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        if isplay:
                            play_hints.append((hint_action, score, hintee_id))
                        self.valid_hints.append((label, hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        self.redun_hints.append((label, hintee_id, score))

            # give the highest-scoring play hint if any, else the
            # highest-scoring valid hint
            if valid and not result:
                self.intent = "Discard"
                if play_hints:
                    valid = play_hints
                    self.intent = "Play"

                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        if not result:
            self.intent = None
        return result, redundant_hints


    def _apply_hint_to_hand(self, hint_action, hand, hand_knowledge):
        """V13: return a copy of one player's card knowledge after receiving
        hint_action, without modifying the original."""
        (action_type, value) = hint_action
        new_knowledge = []
        for (col, num), k in zip(hand, hand_knowledge):
            if action_type == Action.ActionType.HINT_COLOR:
                new_knowledge.append(hint_color(k, value, value == col))
            else:
                new_knowledge.append(hint_rank(k, value, value == num))
        return new_knowledge

    def _has_valid_hint_for(
            self, hintee_knowledge, hintee_intents, hintee_hand, board, trash
    ):
        """V13: True iff at least one intentional hint to this hintee qualifies
        under the baseline pretend() check."""
        hint_action: tuple[Action.ActionType, Color | int]
        for c in Color:
            hint_action = (Action.ActionType.HINT_COLOR, c)
            (isvalid, _, _) = pretend(
                hint_action, hintee_knowledge, hintee_intents, hintee_hand,
                board, trash,
            )
            if isvalid:
                return True
        for r in range(1, 6):
            hint_action = (Action.ActionType.HINT_NUMBER, r)
            (isvalid, _, _) = pretend(
                hint_action, hintee_knowledge, hintee_intents, hintee_hand,
                board, trash,
            )
            if isvalid:
                return True
        return False

    def _next_player_penalty_v13(
            self, hint_action, hands, knowledge, trash, board, hints
    ):
        """
        V13:
        Simulates the next player's turn from their seat, assuming hint_action
        was given. Return (penalty, explanation), where penalty >= 0 is
        subtracted from the hint's score.
        """
        b = self._next_pnr  # the next player, left uninformed
        c = self._sub_pnr  # the subsequent player, the hint's recipient
        tokens_after = hints - 1  # giving this hint spends one token

        # Stage 1: B holds a certainly playable card -> a harmless play.
        b_possible = [get_possible(k) for k in knowledge[b]]
        for p in b_possible:
            if playable(p, board):
                return 0.0, "next player plays a certain card"

        # Stage 2: B holds a certainly useless card -> a harmless discard
        if tokens_after < MAX_HINT_TOKENS:
            for p in b_possible:
                if discardable(p, board):
                    return 0.0, "next player discards a certain useless card"

        # Stage 3: B can give an intentional hint to C
        # Only B's hints to C can be checked
        # B's hints about our own hand cannot, so we pessimistically assume none of those qualify
        if tokens_after > 0:
            c_knowledge = self._apply_hint_to_hand(
                hint_action, hands[c], knowledge[c]
            )
            c_intents = self._create_intents(hands[c], board, trash)
            if self._has_valid_hint_for(
                    c_knowledge, c_intents, hands[c], board, trash
            ):
                return 0.0, "next player can hint the subsequent player"

        # Stage 4: B falls back to the expected-loss discard
        discard_options = [
            Action(Action.ActionType.DISCARD, cnr=i)
            for i in range(len(hands[b]))
        ]
        b_scores = [
            pretend_discard(a, knowledge[b], board, trash)
            for a in discard_options
        ]
        b_scores.sort(key=lambda x: -x[1])
        d = b_scores[0][0].cnr
        (col, rank) = hands[b][d]

        # Critical: the last remaining copy of a card some firework still
        # needs, given the discard pile.
        reach = highest_playable_cards(board, trash)
        still_needed = board[col][1] < rank <= reach[col]
        last_copy = COUNTS[rank - 1] - trash.count((col, rank)) == 1
        if still_needed and last_copy:
            pts_lost = reach[col] - rank + 1
            return (
                V13_CRIT_PENALTY_WEIGHT * pts_lost,
                "next player would discard critical "
                + col.display_name + " " + str(rank),
            )
        return 0.0, "next player's fallback discard is not critical"

    def give_intentional_hint_v13(
            self, nr, hands, knowledge, trash, board, hints, num_players, result
    ):
        """
        V13 (Player-Aware Hint): give_intentional_hint() where every hint
        to the subsequent player pays a flat delay cost plus, if the uninformed
        next player is predicted to discard a critical card, a penalty
        proportional to the points destroyed.

        Hints to the next player keep their baseline score,
        so 2-player games reduce exactly to
        the baseline.

        Return (result, redundant_hints), like give_intentional_hint().
        """
        redundant_hints = []
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            # scores are floats under V13 (adjusted scores), hence the type
            valid: list[tuple[tuple[Action.ActionType, Color | int], float, int]] = []
            redundant_hints = []

            # every colour hint, then every rank hint (same enumeration order
            # as give_intentional_hint)
            candidates: list[tuple[Action.ActionType, Color | int]] = [
                                                                          (Action.ActionType.HINT_COLOR, c) for c in Color
                                                                      ] + [(Action.ActionType.HINT_NUMBER, r) for r in range(1, 6)]

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for hint_action in candidates:
                    (isvalid, score, expl) = pretend(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    if hint_action[0] == Action.ActionType.HINT_COLOR:
                        hint_name = "Hint Color " + hint_action[1].display_name
                        hint_label = hint_action[1].display_name
                    else:
                        hint_name = "Hint Rank " + str(hint_action[1])
                        hint_label = hint_action[1]
                    self.explanation.append(
                        ["Prediction for: " + hint_name]
                        + list(map(format_intention, expl))
                    )

                    if isvalid:
                        score = float(score)
                        # V13: hints to the subsequent player pay the delay
                        # cost and the critical-discard penalty.
                        if num_players == 3 and hintee_id == self._sub_pnr:
                            penalty, why = self._next_player_penalty_v13(
                                hint_action, hands, knowledge, trash, board,
                                hints,
                            )
                            score -= V13_DELAY_COST + penalty
                            self.explanation.append(
                                [
                                    "V13 adjustment for " + hint_name,
                                    "-{:.2f} (delay cost)".format(V13_DELAY_COST),
                                    "-{:.2f} ({})".format(penalty, why),
                                    ]
                            )
                        valid.append((hint_action, score, hintee_id))
                        self.valid_hints.append((hint_label, hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        self.redun_hints.append((hint_label, hintee_id, score))

            if valid and not result:
                # sort descending by adjusted hint score; ties keep
                # enumeration order because Python's sort is stable
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result, redundant_hints

    def give_intentional_hint_v10(
        self, nr, hands, knowledge, trash, board, hints, num_players, result,
        deck_size, lives,
    ):
        """
        V10: give_intentional_hint_v8() with remaining-lives-weighted play
        scoring (Eq. score): the hint's Play contribution is the max
        certainty-scaled w_Play(c) over its Play-aligned cards instead of a
        flat weight summed per card, and that weight is penalized more
        sharply as lives are lost (Eq. wplay, kappa). Discard/May-Discard
        scoring is unchanged from V8.
        Return (result, redundant_hints), like give_intentional_hint().
        """
        redundant_hints = []

        # --- Step 1: assign an intent to each card in each partner's hand ---
        # (identical to give_intentional_hint)
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            # --- Step 2: compute the discard/may-discard weights (from V8) --
            # The Play weight is no longer a single scalar here: it is
            # computed per card inside pretend_v10 from p(c) and kappa(lives).
            initial_draw_pile = TOTAL_CARDS - num_players * self._hand_size
            _, discard_w, may_discard_w = hint_weights_v8(hints, deck_size, initial_draw_pile)
            self.explanation.append(
                [
                    "V10 hint weights",
                    "Discard: {:.2f}".format(discard_w),
                    "May Discard: {:.2f}".format(may_discard_w),
                    "Lives: " + str(lives),
                ]
            )

            # --- Step 3: enumerate and score every legal hint ---------------
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], float, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                # every color hint for this partner
                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend_v10(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                        lives,
                        (discard_w, may_discard_w),
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        self.valid_hints.append(
                            (hint_action[1].display_name, hintee_id, score)
                        )
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        self.redun_hints.append(
                            (hint_action[1].display_name, hintee_id, score)
                        )

                # every rank hint for this partner
                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend_v10(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                        lives,
                        (discard_w, may_discard_w),
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        self.valid_hints.append((hint_action[1], hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        self.redun_hints.append((hint_action[1], hintee_id, score))

            # --- Step 4: give the highest-scoring valid hint ----------------
            # (identical to give_intentional_hint; ties keep enumeration
            # order because Python's sort is stable)
            if valid and not result:
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result, redundant_hints

    def give_hint_v1(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend_v1(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend_v1(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result

    def give_hint_v3(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend_v3(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend_v3(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result



    def play_or_discard(self, nr, knowledge, board, hints, possible, result):
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discardable_idx = []
        for i, p in enumerate(possible):
            if playable(p, board) and not result:
                result = Action(Action.ActionType.PLAY, cnr=i)
            if discardable(p, board):
                discardable_idx.append(i)

        if discardable_idx and hints < MAX_HINT_TOKENS and not result:
            result = Action(
                Action.ActionType.DISCARD, cnr=random.choice(discardable_idx)
            )

        return result

    def play_v2(self, nr, knowledge, board, hints, possible, result, deck_size, lives):
        for i, k in enumerate(knowledge[nr]):
            if playable_v2(k, board, deck_size, lives) and not result:
                result = Action(Action.ActionType.PLAY, cnr=i)
        return result

    def received_hint(self, nr, knowledge, board, hints, result, action):
        (act, plr) = self.got_hint
        if act.action_type == Action.ActionType.HINT_COLOR:
            for k in knowledge[nr]:
                action.append(whattodo(k, sum(k[act.col]) > 0, board))
        elif act.action_type == Action.ActionType.HINT_NUMBER:
            for k in knowledge[nr]:
                cnt = 0
                for c in Color:
                    cnt += k[c][act.num - 1]
                action.append(whattodo(k, cnt > 0, board))

        if action:
            self.explanation.append(
                ["What you want me to do"]
                + [
                    x.display_name if isinstance(x, Action.ActionType) else "Keep"
                    for x in action
                ]
            )
            for i, a in enumerate(action):
                if a == Action.ActionType.PLAY and (
                    not result or result.action_type == Action.ActionType.DISCARD
                ):
                    result = Action(Action.ActionType.PLAY, cnr=i)
                elif a == Action.ActionType.DISCARD and not result and hints < MAX_HINT_TOKENS:
                    result = Action(Action.ActionType.DISCARD, cnr=i)

        self.got_hint = None
        return result

    def _create_intents(
        self,
        hand: list[tuple[Color, int]],
        board: list[tuple[Color, int]],
        trash: list[tuple[Color, int]],
    ) -> list[Intent | None]:
        intentions: list[Intent | None] = [None for _ in range(len(hand))]

        for i, (col, n) in enumerate(hand):
            if board[col][1] + 1 == n:
                intentions[i] = Intent.PLAY
            elif board[col][1] >= n:
                intentions[i] = Intent.DISCARD
            elif n < 5 and n > 1 and (col, n) not in (trash + board):
                # DONE: this condition doesn't account for there being three 1s of each colour
                intentions[i] = Intent.CAN_DISCARD
            elif n == 1:
                count = 0
                for c in (trash + board):
                    if col == c[0] and n == c[1]:
                        count+=1
                if count < 2:
                    intentions[i] = Intent.CAN_DISCARD

        return intentions

    def inform(self, action, player, game):
        if action.pnr == self.pnr and action.action_type in {
            Action.ActionType.HINT_COLOR,
            Action.ActionType.HINT_NUMBER,
        }:
            self.got_hint = (action, player)
            # V5: record whether the giver held eight tokens when giving this
            # hint (making it potentially forced). Versions 0-4 never read
            # this flag, so setting it unconditionally is harmless.
            self.hint_was_forced = (
                self._giver_hint_tokens(game) == MAX_HINT_TOKENS
            )
