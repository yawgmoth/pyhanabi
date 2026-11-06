import sys
from abc import ABCMeta, abstractmethod
from typing import Sequence, override, Final, Any
from collections import Counter

import hana_sim  # type: ignore

from players import Player, HanaSimPlayer
from players.self_intentional import SelfIntentionalPlayer
from utils import (
    Action,
    Color,
    Intent,
    get_possible,
    make_deck,
    initial_knowledge,
    format_hand,
    COUNTS,
    format_card,
    MAX_HINT_TOKENS,
    playable,
)

MAX_PLAYERS: Final[int] = 5
MIN_PLAYERS: Final[int] = 2

type HanaSimAction = tuple[int, int, int, int, list[int], int, int]
type HanaSimCard = tuple[str, int]
type NativeCard = tuple[Color, int]


COLOR_INT_CONVERSION_DICT = {  # converts Hanasim numbering into pyhanabi numbering
    1: Color.RED,
    2: Color.WHITE,
    3: Color.YELLOW,
    4: Color.GREEN,
    5: Color.BLUE,
    6: None,
}

COLOR_REVERSE_CONVERSION_DICT = {v: k for k, v in COLOR_INT_CONVERSION_DICT.items()}


class AbstractGame(metaclass=ABCMeta):
    players: Sequence[Player]

    @abstractmethod
    def __init__(self, players: Sequence[Player], log=sys.stdout):
        self.players = players
        self.log = log

    @abstractmethod
    def run(self, turns: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def single_turn(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def external_turn(self, action: Action) -> None:
        raise NotImplementedError


class HanasimGame(AbstractGame):
    _env: hana_sim.HanabiEnv
    _obs: hana_sim.Observation
    knowledge: list[list[list[list[int]]]]
    _metric_dict: dict[str, Any]
    jlog: dict[str, Any]
    _hinted_cards: dict[int, list[tuple[list[int], Action]]]

    hanasim_colour_map: Final[dict[str, Color]] = {
        "red": Color.RED,
        "white": Color.WHITE,
        "yellow": Color.YELLOW,
        "green": Color.GREEN,
        "blue": Color.BLUE,
    }

    @override
    def __init__(self, players, log=sys.stdout, post_move_metrics: bool = False):
        super().__init__(players, log)
        self._env = hana_sim.HanabiEnv(num_players=len(players))
        self._post_move_metrics = post_move_metrics
        self._metric_dict = {}
        self.jlog = {
            "starting_hands": {},
            "initial_mental_states": {},
            "deck": [],
            "actions": [],
            "result": {},
        }

        for player in self.players:
            if isinstance(player, HanaSimPlayer):
                self._env.add_player(player.hana_sim_name, player.pnr)

        self._reset()

    def _reset(self) -> None:
        self._obs = self._env.reset()
        for p in self.players:
            p.reset()

        hand_size = 4
        if len(self.players) < 4:
            hand_size = 5

        self.knowledge = []
        for i in range(len(self.players)):
            visible_cards = self._get_visible_cards(i, self._obs.hands)
            p_knowledge = []
            for __ in range(hand_size):
                p_knowledge.append(initial_knowledge(visible_cards))

            self.knowledge.append(p_knowledge)

        self._hinted_cards = {}

    @override
    def run(self, turns=-1):
        if not (MIN_PLAYERS <= len(self.players) <= MAX_PLAYERS):
            raise RuntimeError(
                f"Number of players must be between {MIN_PLAYERS} and {MAX_PLAYERS}"
            )

        self._reset()

        # God's-eye starting hands, for tracing the game state.
        print("Starting hands:", file=self.log)
        for i in range(len(self.players)):
            hand = [self._convert_card(c) for c in self._obs.hands[i]]
            self.jlog["starting_hands"][f"player_{i}"] = [
                {"colour": card[0].display_name, "rank": card[1]} for card in hand
            ]
            print(f"Player {i}: {format_hand(hand)}", file=self.log)
        print(
            "==========================================================", file=self.log
        )
        print(file=self.log)  # blank line — paragraph separator

        for i in range(len(self.players)):
            self.jlog["initial_mental_states"][f"player_{i}"] = []
            for card in self.knowledge[i]:
                self.jlog["initial_mental_states"][f"player_{i}"].append(
                    {
                        "green": card[0][:],
                        "yellow": card[1][:],
                        "white": card[2][:],
                        "blue": card[3][:],
                        "red": card[4][:],
                    }
                )

        self.jlog["deck"] = [
            {"color": c[0].display_name, "rank": c[1]}
            for c in self._convert_trash(self._env.deck[:])
        ]

        if self._post_move_metrics:
            # These structures track post-move metrics for each player
            ipp_list = [
                [] for _ in range(len(self.players))
            ]  # list of ipp scores per player for each turn they play/discard
            critical_discards = Counter()  # count of critical discards per player
            all_critical_cards = []
            known_playable_discards = (
                Counter()
            )  # count of known playable discards per player
            known_playable_plays = Counter()  # count of known playable plays per player
            has_playable = (
                Counter()
            )  # count of turns where player had at least one playable card in hand
            known_unplayable_plays = (
                Counter()
            )  # count of known unplayable plays per player
            has_unplayable = (
                Counter()
            )  # count of turns where player had at least one unplayable card in hand
            hint_frequency = Counter()  # count of hints given per player
            hint_possible = Counter()  # count of turns where a hint could be given
            hint_interpreted_correctly = (
                Counter()
            )  # count of hints that were interpreted correctly by the recipient
            hints_received = Counter()  # count of hints received per player

        turn = 1

        while True:
            acting_player_id: int = self._obs.current_player_id

            if not isinstance(self.players[acting_player_id], HanaSimPlayer):
                # Get action from current player based on game state
                action = self.players[acting_player_id].get_action(
                    acting_player_id,
                    self._convert_hands(self._obs.hands, acting_player_id),
                    self.knowledge,
                    self._convert_trash(self._obs.discards),
                    self._convert_played(self._obs.fireworks),
                    self._convert_board(self._obs.fireworks),
                    HanasimGame._convert_valid_actions(self._obs.legal_actions),
                    self._obs.hint_tokens,
                    self._obs.lives_remaining,
                    len(self._env.deck),
                )

                step_result = self._env.step(self._convert_action(action))
            else:
                step_result = self._env.step(None)
                action = self._convert_valid_actions([step_result.last_move])[0]

            # Collect post-move metrics if enabled
            if self._post_move_metrics:
                # Critical discards per play
                critical_discards[acting_player_id] += self._discarding_critical_card(
                    action, acting_player_id
                )
                if (self._all_critical_cards(action, acting_player_id)[0] is not None):
                    all_critical_cards.append(self._all_critical_cards(action, acting_player_id))

                # Known playable discards per play
                known_playable_discards[acting_player_id] += (
                    self._discarding_known_playable_card(action, acting_player_id)
                )

                # Known playable plays per play
                known_playable_plays[acting_player_id] += (
                    self._playing_known_playable_card(action, acting_player_id)
                )

                # Has playable card in hand per turn
                has_playable[acting_player_id] += self._has_playable_card(
                    acting_player_id
                )

                # Known unplayable plays per play
                known_unplayable_plays[acting_player_id] += (
                    self._playing_known_unplayable_card(action, acting_player_id)
                )
                # Has unplayable card in hand per turn
                has_unplayable[acting_player_id] += self._has_unplayable_card(
                    acting_player_id
                )
                # Hints given per player
                hint_frequency[acting_player_id] += (
                    1
                    if action.action_type
                    in [
                        Action.ActionType.HINT_COLOR,
                        Action.ActionType.HINT_NUMBER,
                    ]
                    else 0
                )

                hint_possible[acting_player_id] += 1 if self._obs.hint_tokens > 0 else 0

                hint_interpreted_correctly[acting_player_id] += (
                    self._hint_interpreted_correctly(action, acting_player_id)
                )

                # Hints received per player
                if action.action_type in [
                    Action.ActionType.HINT_COLOR,
                    Action.ActionType.HINT_NUMBER,
                ]:
                    if action.pnr is not None:
                        hints_received[action.pnr] += 1
                    else:
                        hints_received[acting_player_id] += 0

                # Information per play
                if action.action_type in [
                    Action.ActionType.PLAY,
                    Action.ActionType.DISCARD,
                ]:
                    ipp_list[acting_player_id].append(
                        self._information_per_play(action, acting_player_id)
                    )

            self._jlog_action(
                turn, action, acting_player_id, self._obs, step_result.observation
            )

            prev_obs = self._obs
            self._obs = step_result.observation
            self._update_knowledge(
                action,
                acting_player_id,
                self._convert_hands(self._obs.hands, acting_player_id),
                step_result.observation,
                prev_obs,
            )
            self._log_move(turn, action, acting_player_id, prev_obs)

            updated_knowledge = {}
            for i in range(len(self.players)):
                updated_knowledge[f"player_{i}"] = []
                for card in self.knowledge[i]:
                    updated_knowledge[f"player_{i}"].append(
                        {
                            "green": card[0][:],
                            "yellow": card[1][:],
                            "white": card[2][:],
                            "blue": card[3][:],
                            "red": card[4][:],
                        }
                    )

            self.jlog["actions"][-1][f"turn_{turn}"]["resulting_state"][
                "mental_states"
            ] = updated_knowledge
            turn += 1
            if step_result.done:
                break

        board = self._convert_board(self._obs.fireworks)
        points = self._score(board)

        # Classify why the game ended
        if self._obs.lives_remaining == 0:
            end_reason = "out of lives"
        elif all(num == 5 for _, num in board):
            end_reason = "board completed"
        else:
            end_reason = "deck exhausted"

        print("Game done, hits left:", self._obs.lives_remaining, file=self.log)
        print("End reason:", end_reason, file=self.log)
        print("Final Score:", points, file=self.log)

        self.jlog["result"] = {
            "score": points,
            "end_reason": end_reason,
            "lives_remaining": self._obs.lives_remaining,
        }

        if self._post_move_metrics:
            for i in range(len(self.players)):
                if len(ipp_list[i]) == 0:
                    print(
                        f"Player {i} ({self.players[i].name}) IPP: n/a (did not play or discard card)",
                        file=self.log,
                    )
                else:
                    print(
                        f"Player {i} ({self.players[i].name}) IPP: {sum(ipp_list[i]) / len(ipp_list[i]) if ipp_list[i] else 0:.2f}",
                        file=self.log,
                    )
                print(
                    f"Player {i} ({self.players[i].name}) Critical Discards: {critical_discards[i]}",
                    file=self.log,
                )
                print(
                    f"Player {i} ({self.players[i].name}) Known Playable Discards: {known_playable_discards[i]}",
                    file=self.log,
                )
                print(
                    f"Player {i} ({self.players[i].name}) Known Playable Plays: {known_playable_plays[i]}",
                    file=self.log,
                )
                print(
                    f"Player {i} ({self.players[i].name}) Has Playable Cards: {has_playable[i]}",
                    file=self.log,
                )
                print(
                    f"Player {i} ({self.players[i].name}) Known Unplayable Plays: {known_unplayable_plays[i]}",
                    file=self.log,
                )
                print(
                    f"Player {i} ({self.players[i].name}) Has Unplayable Cards: {has_unplayable[i]}",
                    file=self.log,
                )
                print(
                    f"Player {i} ({self.players[i].name}) Hints Given: {hint_frequency[i]}",
                    file=self.log,
                )
                if hint_possible[i] == 0:
                    print(
                        f"Player {i} ({self.players[i].name}) Communicativeness: n/a (no turn with a hint available)",
                        file=self.log,
                    )
                else:
                    print(
                        f"Player {i} ({self.players[i].name}) Communicativeness: {hint_frequency[i] / hint_possible[i]:.2f}",
                        file=self.log,
                    )
            print(f"Critical cards discarded: {all_critical_cards}",
                                file=self.log,
                                            )
            
            self._metric_dict["ipp_list"] = ipp_list
            self._metric_dict["critical_discards"] = critical_discards
            self._metric_dict["critical_cards"] = all_critical_cards
            self._metric_dict["known_discards"] = known_playable_discards
            self._metric_dict["known_playable_plays"] = known_playable_plays
            self._metric_dict["has_playable"] = has_playable
            self._metric_dict["known_unplayable_plays"] = known_unplayable_plays
            self._metric_dict["has_unplayable"] = has_unplayable
            self._metric_dict["hint_frequency"] = hint_frequency
            self._metric_dict["hint_possible"] = hint_possible
            self._metric_dict["hint_interpreted_correctly"] = hint_interpreted_correctly
            self._metric_dict["hints_received"] = hints_received

        return points

    def _summarize_knowledge(self, card_knowledge) -> str:
        """Collapse one card's 5x5 possibility grid into the colors and numbers
        still possible for it — i.e. what its owner knows about it."""
        possible_colors = [
            col.display_name
            for col in Color
            if any(cnt > 0 for cnt in card_knowledge[col])
        ]
        possible_ranks = sorted(
            {
                i + 1
                for col in Color
                for i, cnt in enumerate(card_knowledge[col])
                if cnt > 0
            }
        )
        color = (
            "any" if len(possible_colors) == len(Color) else "/".join(possible_colors)
        )
        rank = (
            "any"
            if len(possible_ranks) == len(COUNTS)
            else "/".join(map(str, possible_ranks))
        )
        return f"color: {color}; number: {rank}"

    def _log_move(self, move_number, action, acting_player_id, prev_obs) -> None:
        """Write one move as a full paragraph: what happened, then the complete
        post-move state (board, trash, tokens, all hands, all mental states)."""
        # What happened this move
        if action.action_type == Action.ActionType.HINT_COLOR:
            print(
                f"Move {move_number}: Player {acting_player_id} hints Player "
                f"{action.pnr}: {action.col.display_name} cards",
                file=self.log,
            )
        elif action.action_type == Action.ActionType.HINT_NUMBER:
            print(
                f"Move {move_number}: Player {acting_player_id} hints Player "
                f"{action.pnr}: {action.num}s",
                file=self.log,
            )
        elif action.action_type == Action.ActionType.PLAY:
            card = self._convert_card(prev_obs.hands[acting_player_id][action.cnr])
            ok = self._obs.lives_remaining == prev_obs.lives_remaining
            print(
                f"Move {move_number}: Player {acting_player_id} plays "
                f"{format_card(card)} — {'successfully' if ok else 'and it failed'}",
                file=self.log,
            )
        else:  # DISCARD
            card = self._convert_card(prev_obs.hands[acting_player_id][action.cnr])
            print(
                f"Move {move_number}: Player {acting_player_id} discards "
                f"{format_card(card)}",
                file=self.log,
            )

        # Shared board state after the move
        board = self._convert_board(self._obs.fireworks)
        trash = self._convert_trash(self._obs.discards)
        print(f"Board: {format_hand(board)}", file=self.log)
        print(f"Trash: {format_hand(trash) if trash else '(empty)'}", file=self.log)
        print(
            f"Lives: {self._obs.lives_remaining} | Hints: {self._obs.hint_tokens}",
            file=self.log,
        )

        # print("Hands:", file=self.log)
        # for i in range(len(self.players)):
        #     hand = [self._convert_card(c) for c in self._obs.hands[i]]
        #     print(f"  Player {i}: {format_hand(hand)}", file=self.log)

        # Every player's hand and mental state
        for i in range(len(self.players)):
            print(f"  Player {i}:", file=self.log)
            for idx, (card, k) in enumerate(zip(self._obs.hands[i], self.knowledge[i])):
                native = self._convert_card(card)
                print(
                    f"    [{idx}] {format_card(native)} -> "
                    f"{self._summarize_knowledge(k)}",
                    file=self.log,
                )

        print(file=self.log)  # blank line — paragraph separator
        print(file=self.log)  # blank line — paragraph separator

    def _jlog_action(self, turn, action, acting_player_id, pre_obs, post_obs):
        p_card = (
            self._convert_card(pre_obs.hands[acting_player_id][action.cnr])
            if action.action_type in [Action.ActionType.PLAY, Action.ActionType.DISCARD]
            else None
        )
        self.jlog["actions"].append(
            {
                f"turn_{turn}": {
                    "player": acting_player_id,
                    "action": {
                        "risky_play": self.players[acting_player_id].get_risky_play(),
                        "discard_crit": self.players[
                            acting_player_id
                        ].get_discard_crit()
                        if isinstance(
                            self.players[acting_player_id], SelfIntentionalPlayer
                        )
                        else None,
                        "critical_hints": [
                            {"hint": h[0], "hinted_player": h[1], "score": h[2]}
                            for h in self.players[acting_player_id].get_critical_hints()
                        ],
                        "type": action.action_type.name,
                        "chosen_card": {
                            "color": p_card[0].display_name,
                            "rank": p_card[1],
                        }
                        if p_card
                        else None,
                        "successful": "no"
                        if post_obs.lives_remaining < pre_obs.lives_remaining
                        else "yes"
                        if action.action_type == Action.ActionType.PLAY
                        else None,
                        "valid_hints": [
                            {"hint": h[0], "hinted_player": h[1], "score": h[2]}
                            for h in self.players[acting_player_id].get_valid_hints()
                        ],
                        "redundant_hints": [
                            {"hint": h[0], "hinted_player": h[1], "score": h[2]}
                            for h in self.players[
                                acting_player_id
                            ].get_redundant_hints()
                        ],
                        "hint": {
                            "hint_intention": self.players[
                            acting_player_id
                        ].get_intent()
                        if isinstance(
                            self.players[acting_player_id], SelfIntentionalPlayer
                        )
                        else None,
                            "hint_color": action.col.display_name
                            if action.col
                            else None,
                            "hint_num": action.num if action.num else None,
                            "hinted_player": action.pnr
                            if action.pnr is not None
                            else None,
                        },
                    },
                    "resulting_state": {
                        "board": [
                            {"color": c[0].display_name, "rank": c[1]}
                            for c in self._convert_board(post_obs.fireworks)
                        ],
                        "discard_pile": [
                            {"color": c[0].display_name, "rank": c[1]}
                            for c in self._convert_trash(post_obs.discards)
                        ],
                        "players_hands": {
                            f"player_{i}": [
                                {"color": c[0].display_name, "rank": c[1]}
                                for c in self._get_resulting_hands(post_obs)[i]
                            ]
                            for i in range(len(self.players))
                        },
                        "mental_states": {},
                        "hint_tokens": post_obs.hint_tokens,
                        "lives_remaining": post_obs.lives_remaining,
                    },
                }
            }
        )

    def _get_resulting_hands(self, post_obs):
        resulting_hands = []
        for i in range(len(self.players)):
            new_hand = [self._convert_card(c) for c in post_obs.hands[i]]
            resulting_hands.append(new_hand)
        return resulting_hands

    def _update_knowledge(
        self,
        action: Action,
        acting_player: int,
        hands: list[list[NativeCard]],
        post_obs,
        prev_obs,
    ) -> None:
        for p in self.players:
            p.inform(action, acting_player, self)

        if action.action_type == Action.ActionType.HINT_COLOR:
            assert action.col is not None
            assert action.pnr is not None

            # Track which cards were hinted
            hinted_indices = []
            for i, (col, rank) in enumerate(hands[action.pnr]):
                if col == action.col:
                    hinted_indices.append(i)
            if action.pnr not in self._hinted_cards:
                self._hinted_cards[action.pnr] = []

            self._hinted_cards[action.pnr].append((hinted_indices, action))

            # Given a hint for colour X,
            # for every card in the hinted player's hand:
            #     - if the card is positively identified, set all non-X cells in the knowledge to 0
            #     - if the card is negatively identified, set all X cells in the knowledge to 0
            for (col, rank), card_knowledge in zip(
                hands[action.pnr], self.knowledge[action.pnr]
            ):
                if col == action.col:
                    for i in range(len(card_knowledge)):
                        if i != col:
                            card_knowledge[i] = [0 for _ in range(len(card_knowledge))]
                else:
                    for i in range(len(card_knowledge[action.col])):
                        card_knowledge[action.col][i] = 0

        elif action.action_type == Action.ActionType.HINT_NUMBER:
            assert action.num is not None
            assert action.pnr is not None

            # Track which cards were hinted
            hinted_indices = []
            for i, (col, rank) in enumerate(hands[action.pnr]):
                if rank == action.num:
                    hinted_indices.append(i)
            if action.pnr not in self._hinted_cards:
                self._hinted_cards[action.pnr] = []

            self._hinted_cards[action.pnr].append((hinted_indices, action))

            # Given a hint for rank N,
            # for every card in the hinted player's hand:
            #     - if the card is positively identified, set all non-N cells in the knowledge to 0
            #     - if the card is negatively identified, set all N cells in the knowledge to 0
            for (col, rank), card_knowledge in zip(
                hands[action.pnr], self.knowledge[action.pnr]
            ):
                if rank == action.num:
                    for k in card_knowledge:
                        for i in range(len(COUNTS)):
                            if i + 1 != rank:
                                k[i] = 0
                else:
                    for k in card_knowledge:
                        k[action.num - 1] = 0

        else:  # the action is either play or discard
            assert action.cnr is not None
            p_card = self._convert_card(prev_obs.hands[acting_player][action.cnr])

            old_col = p_card[0]
            old_rank = p_card[1]

            del self.knowledge[acting_player][action.cnr]
            visible_cards = self._get_visible_cards(acting_player, post_obs.hands)
            self.knowledge[acting_player].append(
                initial_knowledge(visible_cards)
            )  # draw a new card

            # update knowledge of acting player with the card is played/discarded
            for k in self.knowledge[acting_player][:-1]:
                if k[old_col][old_rank - 1] > 0:
                    k[old_col][old_rank - 1] -= 1

            # update knowlege of cooperating players with the new drawn card
            drawn_card = self._convert_card(post_obs.hands[acting_player][-1])
            new_col = drawn_card[0]
            new_rank = drawn_card[1] - 1

            for p in range(len(self.players)):
                if p == acting_player:
                    continue
                for k in self.knowledge[p]:
                    if k[new_col][new_rank] > 0:
                        k[new_col][new_rank] -= 1

    def _get_visible_cards(
        self, player_id, hands: list[list[HanaSimCard]]
    ) -> list[list[NativeCard]]:
        """
        Return the cards player_id can see. The cards it can see are the
        cooperators' hands, discarded cards, cards on the board.
        """
        v = []
        for i in range(len(self.players)):
            if i == player_id:
                continue
            for c in hands[i]:
                v.append(self._convert_card(c))

        for card in self._convert_trash(self._obs.discards):
            v.append(card)

        for c in self._convert_board(self._obs.fireworks):
            for i in range(c[1]):
                v.append((c[0], i + 1))

        return v

    def _convert_hands(
        self, hands: list[list[HanaSimCard]], curr_player: int
    ) -> list[list[NativeCard]]:
        """
        Convert the representation of the current player's hand info from HanaSim's
        type to pyhanabi's type.

        The resulting representation hides the hand of the current player by replacing
        it with an empty list.
        """
        return [
            [] if i == curr_player else [self._convert_card(card) for card in hands[i]]
            for i in range(len(self.players))
        ]

    def _convert_card(self, card: HanaSimCard) -> NativeCard:
        return self.hanasim_colour_map[card[0]], card[1]

    def _convert_trash(self, discard: list[HanaSimCard]) -> list[NativeCard]:
        """
        Convert the representation of the discard pile from HanaSim's type to pyhanabi's type.
        """
        return [self._convert_card(card) for card in discard]

    def _convert_played(self, fireworks: dict[str, int]) -> list[NativeCard]:
        """
        Convert the representation of the played cards from HanaSim's type to pyhanabi's type.
        """
        return [
            self._convert_card((color, i))
            for color in fireworks
            for i in range(1, fireworks[color] + 1)
        ]

    def _convert_board(self, fireworks: dict[str, int]) -> list[NativeCard]:
        """
        Convert the representation of the fireworks constructed on the board from
        HanaSim's type to pyhanabi's type.
        """
        return sorted(
            [self._convert_card((color, fireworks[color])) for color in fireworks]
        )

    @staticmethod
    def _convert_valid_actions(legal_actions: list[HanaSimAction]) -> list[Action]:
        """
        Convert the representation of legal actions from HanaSim's type to the Action
        type used in pyhanabi.
        """
        actions = []
        for action in legal_actions:
            if action[0] == 1:  # color hint
                move_type = Action.ActionType.HINT_COLOR
            elif action[0] == 2:  # rank hint
                move_type = Action.ActionType.HINT_NUMBER
            elif action[0] == 3:  # play
                move_type = Action.ActionType.PLAY
            elif action[0] == 4:  # discard
                move_type = Action.ActionType.DISCARD
            else:
                continue

            if move_type is Action.ActionType.HINT_COLOR:
                if COLOR_INT_CONVERSION_DICT[action[5]] is not None:
                    actions.append(
                        Action(
                            action_type=move_type,
                            pnr=action[1],
                            col=COLOR_INT_CONVERSION_DICT[action[5]],
                        )
                    )
            elif move_type is Action.ActionType.HINT_NUMBER:
                actions.append(
                    Action(action_type=move_type, pnr=action[1], num=action[6])
                )
            else:
                actions.append(Action(action_type=move_type, cnr=action[3]))
        return actions

    def _convert_action(self, native_action: Action) -> HanaSimAction:
        """
        Convert a pyhanabi Action object to HanaSim's action representation.
        """
        a_type = native_action.action_type
        if a_type is Action.ActionType.HINT_COLOR:
            move_type = 1
        elif a_type is Action.ActionType.HINT_NUMBER:
            move_type = 2
        elif a_type is Action.ActionType.PLAY:
            move_type = 3
        elif a_type is Action.ActionType.DISCARD:
            move_type = 4
        else:
            move_type = 5  # INVALID_MOVE

        # for hints we fill in `to_` & `card_indices`, for non‐hints it's -1 and empty
        color, rank = 6, 6  # 6 represents invalid color and rank
        if move_type == 1:  # color hint
            assert native_action.pnr is not None
            to_ = native_action.pnr
            card_indices = []
            for i, card in enumerate(self._obs.hands[to_]):
                card = self._convert_card(card)
                if card[0] == native_action.col:
                    card_indices.append(i)
            card_index = -1
            color = COLOR_REVERSE_CONVERSION_DICT[native_action.col]
        elif move_type == 2:  # rank hint
            assert native_action.num is not None
            assert native_action.pnr is not None
            to_ = native_action.pnr
            card_indices = []
            for i, card in enumerate(self._obs.hands[to_]):
                card = self._convert_card(card)
                if card[1] == native_action.num:
                    card_indices.append(i)
            card_index = -1
            rank = native_action.num
        else:  # play or discard
            to_ = -1
            card_indices = []
            card_index = native_action.cnr if native_action.cnr is not None else -1

        # `from_` is the active player issuing this action
        from_ = self._obs.current_player_id

        return move_type, to_, from_, card_index, card_indices, color, rank

    @staticmethod
    def _score(board) -> int:
        return sum(list(map(lambda x: x[1], board)))

    @override
    def single_turn(self):
        """
        Assume the player is a pyhanabi player or a hanasim agent.
        """
        if not self._obs.done():
            action = self.players[self._obs.current_player_id].get_action(
                self._obs.current_player_id,
                self._convert_hands(self._obs.hands, self._obs.current_player_id),
                self.knowledge,
                self._convert_trash(self._obs.discard),
                self._convert_played(self._obs.fireworks),
                self._convert_board(self._obs.fireworks),
                HanasimGame._convert_valid_actions(self._obs.legal_actions),
                self._obs.hint_tokens,
            )
            acting_player_id: int = self._obs.current_player_id
            self._obs = self._env.step(self._convert_action(action))
            self._update_knowledge(
                action,
                acting_player_id,
                self._convert_hands(self._obs.hands, self._obs.current_player_id),
            )

    @override
    def external_turn(self, action: Action):
        """
        Assume the current player is a human player.
        """
        if not self._obs.done():
            acting_player_id: int = self._obs.current_player_id
            self._obs = self._env.step(self._convert_action(action))
            self._update_knowledge(
                action,
                acting_player_id,
                self._convert_hands(self._obs.hands, self._obs.current_player_id),
            )

    def _discarding_critical_card(self, action: Action, acting_player_id: int) -> bool:
        """
        This returns True if a player has discarded a critical card
        """

        # If action is not a discard, it is irrelevant to the calculation
        if action.action_type != Action.ActionType.DISCARD:
            return False

        # Identify card number and colour
        (col, num) = self._convert_card(self._obs.hands[acting_player_id][action.cnr])

        # a 5 card is always critical
        if num == 5:
            return True

        # Check how many instances of the card are in the discard pile
        trash = self._convert_trash(self._obs.discards)
        count = 0
        for card in trash:
            if card[0] == col and card[1] == num:
                count += 1

        # Determine if discard is critical based on card number
        if num == 1 and count == 2:
            return True
        if (num == 2 or num == 3 or num == 4) and count == 1:
            return True

        return False
    
    def _all_critical_cards(self, action: Action, acting_player_id: int) -> bool:
            """
            This returns the card if a player has discarded a critical card
            """
    
            # If action is not a discard, it is irrelevant to the calculation
            if action.action_type != Action.ActionType.DISCARD:
                return [None, None]
    
            # Identify card number and colour
            (col, num) = self._convert_card(self._obs.hands[acting_player_id][action.cnr])
    
            # a 5 card is always critical
            if num == 5:
                return [col.display_name, num]
    
            # Check how many instances of the card are in the discard pile
            trash = self._convert_trash(self._obs.discards)
            count = 0
            for card in trash:
                if card[0] == col and card[1] == num:
                    count += 1
    
            # Determine if discard is critical based on card number
            if num == 1 and count == 2:
                return [col.display_name, num]
            if (num == 2 or num == 3 or num == 4) and count == 1:
                return [col.display_name, num]
    
            return [None, None]

    def _discarding_known_playable_card(
        self, action: Action, acting_player_id: int
    ) -> bool:
        """
        This returns True if a player has discarded a known-to-be-playable card
        """
        # If action is not a discard, it is irrelevant to the calculation
        if action.action_type != Action.ActionType.DISCARD:
            return False

        # Check if the card is playable
        possible_cards = get_possible(self.knowledge[acting_player_id][action.cnr])
        return playable(possible_cards, self._convert_board(self._obs.fireworks))

    def _playing_known_playable_card(
        self, action: Action, acting_player_id: int
    ) -> bool:
        """
        This returns True if a player has played a known-to-be-playable card
        """
        # If action is not a play, it is irrelevant to the calculation
        if action.action_type != Action.ActionType.PLAY:
            return False

        # Check if the card is playable
        possible_cards = get_possible(self.knowledge[acting_player_id][action.cnr])
        return playable(possible_cards, self._convert_board(self._obs.fireworks))

    def _has_playable_card(self, acting_player_id: int) -> bool:
        """
        This returns True if a player has at least one playable card in their
        current hand
        """
        for i in range(len(self.knowledge[acting_player_id])):
            # check if the card is playable
            possible_cards = get_possible(self.knowledge[acting_player_id][i])
            if playable(possible_cards, self._convert_board(self._obs.fireworks)):
                return True
        return False

    def _playing_known_unplayable_card(
        self, action: Action, acting_player_id: int
    ) -> bool:
        """
        This returns True if a player has played a known-to-be-unplayable card
        """
        # If action is not a play, it is irrelevant to the calculation
        if action.action_type != Action.ActionType.PLAY:
            return False

        # Check if the card is unplayable
        possible_cards = get_possible(self.knowledge[acting_player_id][action.cnr])
        return not playable(possible_cards, self._convert_board(self._obs.fireworks))

    def _has_unplayable_card(self, acting_player_id: int) -> bool:
        """
        This returns True if a player has at least one unplayable card in their
        current hand
        """
        for i in range(len(self.knowledge[acting_player_id])):
            # check if the card is unplayable
            possible_cards = get_possible(self.knowledge[acting_player_id][i])
            if not playable(possible_cards, self._convert_board(self._obs.fireworks)):
                return True
        return False

    def _hint_interpreted_correctly(
        self, action: Action, acting_player_id: int
    ) -> bool:
        """
        This returns True if a player has interpreted a hint correctly
        i.e. If the card is playable, it should have been played (not discarded),
        if the card is discardable (and not playable), it should have been discarded
        or kept.
        """
        # Only evaluate plays and discards
        if action.action_type not in {
            Action.ActionType.PLAY,
            Action.ActionType.DISCARD,
        }:
            return False

        # Check if this player has any hinted cards
        if (
            acting_player_id not in self._hinted_cards
            or not self._hinted_cards[acting_player_id]
        ):
            return False

        card_index = action.cnr

        # Check if the card index is in the hinted cards
        hint_index = None
        for i, (hinted_indices, hint_action) in enumerate(
            self._hinted_cards[acting_player_id]
        ):
            if card_index in hinted_indices:
                hint_index = i
                break

        if hint_index is None:
            return False  # The card played/discarded was not hinted at

        hinted_indices, hint_action = self._hinted_cards[acting_player_id][hint_index]
        del self._hinted_cards[acting_player_id][hint_index]

        actual_card = self._convert_card(self._obs.hands[acting_player_id][card_index])
        intention = None
        board = self._convert_board(self._obs.fireworks)
        trash = self._convert_trash(self._obs.discards)
        if board[actual_card[0]][1] + 1 == actual_card[1]:
            intention = Intent.PLAY
        elif board[actual_card[0]][1] >= actual_card[1]:
            intention = Intent.DISCARD
        elif (
            actual_card[1] < 5
            and actual_card[1] > 1
            and (actual_card[0], actual_card[1]) not in (trash + board)
        ):
            # DONE: this condition doesn't account for there being three 1s of each colour
            intention = Intent.CAN_DISCARD
        elif actual_card[1] == 1:
            count = 0
            for c in trash + board:
                if actual_card[0] == c[0] and actual_card[1] == c[1]:
                    count += 1
            if count < 2:
                intention = Intent.CAN_DISCARD

        if action.action_type == Action.ActionType.PLAY and intention == Intent.PLAY:
            return True

        elif action.action_type == Action.ActionType.DISCARD and intention in {
            Intent.DISCARD,
            Intent.CAN_DISCARD,
        }:
            return True
        return False

    def _information_per_play(self, action: Action, acting_player_id: int) -> float:
        total_info = 0

        possible_cards = get_possible(self.knowledge[acting_player_id][action.cnr])

        if len(possible_cards) == 1:
            total_info = 2
        else:
            colour = True
            rank = True
            # check colour
            for i in range(1, len(possible_cards)):
                if possible_cards[i][0] != possible_cards[i - 1][0]:
                    colour = False
                    break

            for i in range(1, len(possible_cards)):
                if possible_cards[i][1] != possible_cards[i - 1][1]:
                    rank = False
                    break

            if colour:
                total_info += 1

            if rank:
                total_info += 1

        return total_info / 2

    @property
    def metric_dict(self) -> dict[str, list]:
        "Retrieve a dict of metrics to display results once the game has finished"
        return self._metric_dict


class Game(AbstractGame):
    @override
    def __init__(self, players, log=sys.stdout, format=0):
        super().__init__(players)
        self.hits = 3
        self.hints = MAX_HINT_TOKENS
        self.current_player = 0
        self.board = [(c, 0) for c in Color]
        self.played = []
        self.deck = make_deck()
        self.extra_turns = 0
        self.hands = []
        self.knowledge = []
        self.make_hands()
        self.trash = []
        self.log = log
        self.turn = 1
        self.format = format
        self.dopostsurvey = False
        self.study = False
        if self.format:
            print(self.deck, file=self.log)

    def make_hands(self):
        handsize = 4
        if len(self.players) < 4:
            handsize = 5
        for i, p in enumerate(self.players):
            self.hands.append([])
            self.knowledge.append([])
            for j in list(range(handsize)):
                self.draw_card(i)

    def draw_card(self, pnr=None):
        if pnr is None:
            pnr = self.current_player
        if not self.deck:
            return
        self.hands[pnr].append(self.deck[0])
        self.knowledge[pnr].append(initial_knowledge())
        del self.deck[0]

    def perform(self, action: Action):
        for p in self.players:
            p.inform(action, self.current_player, self)
        if self.format:
            print(
                "MOVE:",
                self.current_player,
                action.action_type,
                action.cnr,
                action.pnr,
                action.col,
                action.num,
                file=self.log,
            )
        if action.action_type == Action.ActionType.HINT_COLOR:
            assert action.col is not None
            assert action.pnr is not None

            self.hints -= 1
            print(
                self.players[self.current_player].name,
                "hints",
                self.players[action.pnr].name,
                "about all their",
                action.col.display_name,
                "cards",
                "hints remaining:",
                self.hints,
                file=self.log,
            )
            print(
                self.players[action.pnr].name,
                "has",
                format_hand(self.hands[action.pnr]),
                file=self.log,
            )
            for (col, num), knowledge in zip(
                self.hands[action.pnr], self.knowledge[action.pnr]
            ):
                if col == action.col:
                    for i, k in enumerate(knowledge):
                        if i != col:
                            for i in range(len(k)):
                                k[i] = 0
                else:
                    for i in range(len(knowledge[action.col])):
                        knowledge[action.col][i] = 0
        elif action.action_type == Action.ActionType.HINT_NUMBER:
            assert action.num is not None
            assert action.pnr is not None

            self.hints -= 1
            print(
                self.players[self.current_player].name,
                "hints",
                self.players[action.pnr].name,
                "about all their",
                action.num,
                "hints remaining:",
                self.hints,
                file=self.log,
            )
            print(
                self.players[action.pnr].name,
                "has",
                format_hand(self.hands[action.pnr]),
                file=self.log,
            )
            for (col, num), knowledge in zip(
                self.hands[action.pnr], self.knowledge[action.pnr]
            ):
                if num == action.num:
                    for k in knowledge:
                        for i in range(len(COUNTS)):
                            if i + 1 != num:
                                k[i] = 0
                else:
                    for k in knowledge:
                        k[action.num - 1] = 0
        elif action.action_type == Action.ActionType.PLAY:
            (col, num) = self.hands[self.current_player][action.cnr]
            print(
                self.players[self.current_player].name,
                "plays",
                format_card((col, num)),
                file=self.log,
            )
            if self.board[col][1] == num - 1:
                self.board[col] = (col, num)
                self.played.append((col, num))
                if num == 5:
                    self.hints += 1
                    self.hints = min(self.hints, 8)
                print(
                    "successfully! Board is now", format_hand(self.board), file=self.log
                )
            else:
                self.trash.append((col, num))
                self.hits -= 1
                print("and fails. Board was", format_hand(self.board), file=self.log)
            del self.hands[self.current_player][action.cnr]
            del self.knowledge[self.current_player][action.cnr]
            self.draw_card()
            print(
                self.players[self.current_player].name,
                "now has",
                format_hand(self.hands[self.current_player]),
                file=self.log,
            )
        else:
            self.hints += 1
            self.hints = min(self.hints, 8)
            self.trash.append(self.hands[self.current_player][action.cnr])
            print(
                self.players[self.current_player].name,
                "discards",
                format_card(self.hands[self.current_player][action.cnr]),
                file=self.log,
            )
            print("trash is now", format_hand(self.trash), file=self.log)
            del self.hands[self.current_player][action.cnr]
            del self.knowledge[self.current_player][action.cnr]
            self.draw_card()
            print(
                self.players[self.current_player].name,
                "now has",
                format_hand(self.hands[self.current_player]),
                file=self.log,
            )

    def valid_actions(self):
        valid = []
        for i in range(len(self.hands[self.current_player])):
            valid.append(Action(Action.ActionType.PLAY, cnr=i))
            valid.append(Action(Action.ActionType.DISCARD, cnr=i))
        if self.hints > 0:
            for i, p in enumerate(self.players):
                if i != self.current_player:
                    for col in set(list(map(lambda x: x[0], self.hands[i]))):
                        valid.append(
                            Action(Action.ActionType.HINT_COLOR, pnr=i, col=col)
                        )
                    for num in set(list(map(lambda x: x[1], self.hands[i]))):
                        valid.append(
                            Action(Action.ActionType.HINT_NUMBER, pnr=i, num=num)
                        )
        return valid

    @override
    def run(self, turns=-1):
        for p in self.players:
            p.reset()
        self.turn = 1
        while not self.done() and (turns < 0 or self.turn < turns):
            self.turn += 1
            if not self.deck:
                self.extra_turns += 1
            hands: list[list[NativeCard]] = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(
                self.current_player,
                hands,
                self.knowledge,
                self.trash,
                self.played,
                self.board,
                self.valid_actions(),
                self.hints,
            )
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)
        print("Game done, hits left:", self.hits, file=self.log)
        points = self.score()
        print("Points:", points, file=self.log)
        return points

    def score(self):
        return sum(list(map(lambda x: x[1], self.board)))

    @override
    def single_turn(self):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            hands: list[list[NativeCard]] = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(
                self.current_player,
                hands,
                self.knowledge,
                self.trash,
                self.played,
                self.board,
                self.valid_actions(),
                self.hints,
            )
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)

    @override
    def external_turn(self, action):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)

    def done(self):
        if self.extra_turns == len(self.players) or self.hits == 0:
            return True
        for col, num in self.board:
            if num != 5:
                return False
        return True

    def finish(self):
        if self.format:
            print("Score", self.score(), file=self.log)
            self.log.close()
