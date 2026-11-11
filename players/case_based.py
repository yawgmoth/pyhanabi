import random
from dataclasses import dataclass
from typing import Final, override

from players import Player
from utils import (
    COUNTS,
    MAX_HINT_TOKENS,
    TOTAL_CARDS,
    Action,
    Color,
    Intent,
    discard_utility_v17,
    discardable,
    get_possible,
    hint_color,
    hint_rank,
    hint_weights_v8,
    life_cost_v17,
    play_utility_v17,
    playable,
    potentially_discardable,
    potentially_playable,
    pretend_discard,
    whattodo,
)

PLAY: Final = Action.ActionType.PLAY
DISCARD: Final = Action.ActionType.DISCARD
HINT_COLOR: Final = Action.ActionType.HINT_COLOR
HINT_NUMBER: Final = Action.ActionType.HINT_NUMBER

PLAY_SCORE: Final = 3
DISCARD_SCORE: Final = 2
MAY_DISCARD_SCORE: Final = 1
REJECTED: Final = float("-inf")

# Static (play, discard, may discard) weights of Algorithm 7.
STATIC_WEIGHTS: Final[tuple[float, float, float]] = (
    float(PLAY_SCORE),
    float(DISCARD_SCORE),
    float(MAY_DISCARD_SCORE),
)

# Minimum tokens for the second critical-hint stage (V19's V19_CRIT_HINT_MIN_TOKENS).
CRIT_INFO_MIN_TOKENS: Final = 4


def is_hint(action: Action) -> bool:
    return action.action_type in (HINT_COLOR, HINT_NUMBER)


def hint_to(action: Action | None, player: int) -> Action | None:
    """Return action if it is a hint to player, otherwise None."""
    if action is not None and is_hint(action) and action.pnr == player:
        return action
    return None


def identifies(hint: Action, card: tuple[Color, int]) -> bool:
    """Return True iff hint positively identifies a visible card."""
    col, rank = card
    if hint.action_type is HINT_COLOR:
        return col == hint.col
    return rank == hint.num


def was_identified(hint: Action, table: list[list[int]]) -> bool:
    """Return True iff hint positively identified a hidden card, from its knowledge."""
    if hint.action_type is HINT_COLOR:
        assert hint.col is not None
        return any(table[hint.col])
    assert hint.num is not None
    return any(row[hint.num - 1] for row in table)


def apply_hint(
    hint: Action, hand: list[tuple[Color, int]], knowledge: list[list[list[int]]]
) -> list[list[list[int]]]:
    if hint.action_type is HINT_COLOR:
        return [
            hint_color(table, hint.col, col == hint.col)
            for (col, _), table in zip(hand, knowledge)
        ]
    return [
        hint_rank(table, hint.num, rank == hint.num)
        for (_, rank), table in zip(hand, knowledge)
    ]


def is_expendable(card: tuple[Color, int], trash: list[tuple[Color, int]]) -> bool:
    """Another copy remains. Only for cards that are not useless."""
    return COUNTS[card[1] - 1] - trash.count(card) >= 2


def is_critical(
    card: tuple[Color, int],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> bool:
    """Last copy of a card the board still needs (Section 6.11)."""
    return card[1] > board[card[0]][1] and not is_expendable(card, trash)


def giver_hint_tokens(game) -> int:
    """Tokens the giver held when hinting: HanasimGame informs post-action, Game pre-action."""
    obs = getattr(game, "_obs", None)
    if obs is not None:
        return min(obs.hint_tokens + 1, MAX_HINT_TOKENS)
    return game.hints


def identities_removed(
    hand: list[tuple[Color, int]], knowledge: list[list[list[int]]], rank: int
) -> int:
    """Identities a rank hint removes from a hand's mental state (Section 6.7)."""
    removed = 0
    for (_, num), table in zip(hand, knowledge):
        if num == rank:
            removed += sum(
                1
                for col in Color
                for i in range(len(COUNTS))
                if i + 1 != rank and table[col][i] > 0
            )
        else:
            removed += sum(1 for col in Color if table[col][rank - 1] > 0)
    return removed


def forced_rank_hint(
    a: int,
    hands: list[list[tuple[Color, int]]],
    knowledge: list[list[list[list[int]]]],
    board: list[tuple[Color, int]],
) -> Action | None:
    """The forced rank hint of Section 6.7: a rank no firework awaits, removing the most identities."""
    awaited = {board[col][1] + 1 for col in Color if board[col][1] < 5}
    candidates = []
    for player, hand in enumerate(hands):
        if player == a:
            continue
        for rank in sorted({rank for (_, rank) in hand}):
            removed = identities_removed(hand, knowledge[player], rank)
            candidates.append((rank not in awaited, removed, player, rank))
    if not candidates:
        return None
    _, _, player, rank = max(candidates, key=lambda c: (c[0], c[1]))
    return Action(HINT_NUMBER, pnr=player, num=rank)


def assign_goals(
    hand: list[tuple[Color, int]],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> list[Intent | None]:
    """Goals I_i"""
    goals: list[Intent | None] = []
    for col, rank in hand:
        top = board[col][1]
        if rank == top + 1:
            goals.append(Intent.PLAY)
        elif rank <= top:
            goals.append(Intent.DISCARD)
        elif is_expendable((col, rank), trash):
            goals.append(Intent.CAN_DISCARD)
        else:
            goals.append(None)
    return goals


def predict(
    knowledge: list[list[list[int]]],
    touched: list[bool],
    board: list[tuple[Color, int]],
) -> list[Action.ActionType | None]:
    """
    PREDICT (Algorithm 1)
    Precondition: The hint is already applied to knowledge.
    """
    return [whattodo(table, hit, board) for table, hit in zip(knowledge, touched)]


def alignment_score(
    goals: list[Intent | None],
    predictions: list[Action.ActionType | None],
    weights: tuple[float, float, float] = STATIC_WEIGHTS,
) -> float:
    """S (Algorithm 7). ``weights`` is (play, discard, may discard)."""
    play_w, discard_w, may_discard_w = weights
    total = 0.0
    for goal, predicted in zip(goals, predictions):
        if predicted is PLAY and goal is not Intent.PLAY:
            return REJECTED
        if predicted is DISCARD and goal in (Intent.PLAY, None):
            return REJECTED
        if predicted is PLAY:
            total += play_w
        elif predicted is DISCARD:
            total += discard_w if goal is Intent.DISCARD else may_discard_w
    return total


def response_utility(
    hint: Action,
    action: Action,
    knowledge: list[list[list[int]]],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> int:
    """U (Algorithm 6). knowledge is A's own hand."""
    if action.action_type not in (PLAY, DISCARD):
        return 0
    assert action.cnr is not None
    table = knowledge[action.cnr]
    if not was_identified(hint, table):
        return 0
    possible = get_possible(table)
    if action.action_type is PLAY:
        return PLAY_SCORE if potentially_playable(possible, board) else 0
    if potentially_discardable(possible, board):
        return DISCARD_SCORE
    if any(is_expendable(card, trash) for card in possible):
        return MAY_DISCARD_SCORE
    return 0


def outcomes(
    action: Action,
    table: list[list[int]],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> list[tuple[int, list[tuple[Color, int]], list[tuple[Color, int]]]]:
    """(weight, board, trash) for each identity a played or discarded card may have."""
    results = []
    for col in Color:
        for i, count in enumerate(table[col]):
            if count <= 0:
                continue
            card = (col, i + 1)
            if action.action_type is PLAY and board[col][1] + 1 == card[1]:
                new_board = board[:]
                new_board[col] = card
                results.append((count, new_board, trash))
            else:
                results.append((count, board, trash + [card]))
    return results


@dataclass(frozen=True)
class _Turn:
    a: int
    b: int
    c: int
    hands: list[list[tuple[Color, int]]]
    knowledge: list[list[list[list[int]]]]
    trash: list[tuple[Color, int]]
    board: list[tuple[Color, int]]
    tokens: int
    legal: list[Action]
    # Weights for S inside the hint heuristic H; S and U are static elsewhere.
    hint_weights: tuple[float, float, float] = STATIC_WEIGHTS
    # Absent on engines that do not pass them (legacy Game, GUI, converter).
    lives: int | None = None
    deck_size: int | None = None


@dataclass
class _Candidate:
    action: Action
    utility: float = 0.0  # sum of U over the hints A received
    plan: float = 0.0  # S(I_B, A^_B) after the action
    hint_score: float = 0.0  # H, used only to rank hints
    crit_save: bool = False  # identifies the critical card a partner may discard (V9)

    @property
    def objective(self) -> float:
        return self.utility + self.plan


class CaseBasedPlayer(Player):
    def __init__(self, name: str, pnr: int):
        super().__init__(name, pnr)

        ############ Switches ##############
        # V8 dynamic weights for H; False recovers the fixed 3/2/1 weighting.
        self.dynamic_hint_weights: bool = True
        # V5 forced hints; False recovers redundant/random giving and full interpretation.
        self.forced_hint: bool = True
        # V9/V19 critical card hints; False recovers HEAD behavior.
        self.critical_card_hints: bool = True
        # V17 risky play before the fallback discard; False recovers HEAD behavior.
        self.risky_play: bool = True


        self._last_actions: dict[int, Action] = {}  # a_B and a_C
        self._was_forced: dict[int, bool] = {}  # giver held eight tokens when hinting
        self.case: str | None = None
        self.valid_hints: list[tuple[str | int, int, float]] = []
        self.redun_hints: list[tuple[str | int, int, float]] = []
        self.crit_hints: list[tuple[str | int, int, float]] = []
        self.played_risky: bool = False  # this turn's action is a V17 risky play

    @override
    def reset(self) -> None:
        self._last_actions = {}
        self._was_forced = {}
        self.case = None
        self.valid_hints = []
        self.redun_hints = []
        self.crit_hints = []
        self.played_risky = False

    # Read by the game's JSON log.
    def get_valid_hints(self):
        return self.valid_hints

    def get_redundant_hints(self):
        return self.redun_hints

    def get_critical_hints(self):
        return self.crit_hints

    @override
    def get_risky_play(self):
        return self.played_risky

    @override
    def inform(self, action: Action, player: int, game) -> None:
        if player == self.pnr:
            self._last_actions = {}
            self._was_forced = {}
        else:
            self._last_actions[player] = action
            self._was_forced[player] = (
                is_hint(action) and giver_hint_tokens(game) == MAX_HINT_TOKENS
            )

    @override
    def get_action(
        self,
        nr,
        hands,
        knowledge,
        trash,
        played,
        board,
        valid_actions,
        hints,
        lives=None,
        deck_size=None,
    ) -> Action:
        """Algorithm 8."""
        num_players = len(knowledge)
        if self.dynamic_hint_weights and deck_size is not None:
            # V8: weights computed once from the state at the start of A's turn.
            initial_draw_pile = TOTAL_CARDS - num_players * self._hand_size
            hint_weights = hint_weights_v8(hints, deck_size, initial_draw_pile)
        else:
            hint_weights = STATIC_WEIGHTS
        turn = _Turn(
            a=nr,
            b=(nr + 1) % num_players,
            c=(nr - 1) % num_players,
            hands=hands,
            knowledge=knowledge,
            trash=trash,
            board=board,
            tokens=hints,
            legal=valid_actions,
            hint_weights=hint_weights,
            lives=lives,
            deck_size=deck_size,
        )
        self.case = None
        self.valid_hints = []
        self.redun_hints = []
        self.crit_hints = []
        self.played_risky = False
        self.explanation = []
        self.explanation.append(
            [
                "Hint weights (H)",
                "Play: {:.2f}".format(hint_weights[0]),
                "Discard: {:.2f}".format(hint_weights[1]),
                "May Discard: {:.2f}".format(hint_weights[2]),
            ]
        )

        # Lines 2-4
        for action in turn.legal:
            if action.action_type is PLAY:
                possible = get_possible(knowledge[nr][action.cnr])
                if possible and playable(possible, board):
                    self.explanation.append(["Certainly playable", str(action)])
                    return action

        # Lines 5-21
        self.case, received, plan = self._classify(turn)
        candidates, redundant = self._candidates(turn, received, plan)
        self._explain(candidates)
        if not candidates:
            # Full hint bank and no intentional hint: the rank hint of
            # Section 6.7 (V5), or Algorithm 2 lines 19-21 when V5 is off.
            if self.forced_hint:
                forced = forced_rank_hint(turn.a, turn.hands, turn.knowledge, turn.board)
                if forced is not None:
                    self.explanation.append(["Forced rank hint", str(forced)])
                    return forced
            return random.choice(redundant or [a for a in turn.legal if is_hint(a)])
        best = max(candidate.objective for candidate in candidates)
        top = [candidate for candidate in candidates if candidate.objective == best]

        # Lines 22-23, also used to break ties
        return self._baseline_choice(turn, top, plan)

    def _intended(self, player: int) -> Action | None:
        """The player's last action, unless it was a hint that may have been forced (V5)."""
        if self.forced_hint and self._was_forced.get(player):
            self.explanation.append(
                ["Hint from player " + str(player) + " may have been forced "
                 "(giver held 8 tokens): intention not interpreted"]
            )
            return None
        return self._last_actions.get(player)

    def _classify(self, turn: _Turn) -> tuple[str, list[Action], Action | None]:
        """Returns (case, hints A received, C's pending hint to B)."""
        a_b = self._intended(turn.b)
        a_c = self._intended(turn.c) if turn.c != turn.b else None
        b_to_a = hint_to(a_b, turn.a)
        c_to_a = hint_to(a_c, turn.a)
        c_to_b = hint_to(a_c, turn.b)

        if b_to_a and c_to_a:
            return "1a", [b_to_a, c_to_a], None
        if b_to_a and c_to_b:
            return "1b", [b_to_a], c_to_b
        if b_to_a:
            return "1c", [b_to_a], None
        if c_to_a:
            return "2a", [c_to_a], None
        if c_to_b:
            return "2b", [], c_to_b
        return "2c", [], None

    def _candidates(
        self, turn: _Turn, received: list[Action], plan: Action | None
    ) -> tuple[list[_Candidate], list[Action]]:
        """Returns (candidates with objective terms, redundant hints)."""
        own = turn.knowledge[turn.a]
        candidates = []
        for action in turn.legal:
            kind = action.action_type
            if kind is DISCARD and turn.tokens >= MAX_HINT_TOKENS:
                continue
            if kind in (PLAY, DISCARD):
                utility = sum(
                    response_utility(hint, action, own, turn.board, turn.trash)
                    for hint in received
                )
                # Plays with no hint behind them are not candidates.
                if kind is DISCARD or utility > 0:
                    candidates.append(_Candidate(action, utility=utility))
        hints, redundant = self._intentional_hints(turn, plan)
        candidates.extend(hints)
        if self.critical_card_hints:
            self._mark_critical_saves(turn, plan, candidates)

        if plan is not None:
            for candidate in candidates:
                candidate.plan = self._plan_after(turn, plan, candidate.action)
            # If S is -inf whatever A does, it gives no guidance.
            if all(candidate.plan == REJECTED for candidate in candidates):
                for candidate in candidates:
                    candidate.plan = 0.0
        return candidates, redundant

    def _plan_after(self, turn: _Turn, plan: Action, action: Action) -> float:
        """S(I_B, A^_B) for C's hint ``plan`` in the state resulting from ``action``."""
        hand = turn.hands[turn.b]
        knowledge = turn.knowledge[turn.b]
        states = [(1, turn.board, turn.trash)]
        if is_hint(action):
            if action.pnr == turn.b:
                knowledge = apply_hint(action, hand, knowledge)
        else:
            assert action.cnr is not None
            table = turn.knowledge[turn.a][action.cnr]
            states = outcomes(action, table, turn.board, turn.trash) or states

        touched = [identifies(plan, card) for card in hand]
        weight_of: dict[float, int] = {}
        for weight, board, trash in states:
            value = alignment_score(
                assign_goals(hand, board, trash), predict(knowledge, touched, board)
            )
            weight_of[value] = weight_of.get(value, 0) + weight
        # A's card is hidden: take the most likely value, the worse one on ties.
        return max(weight_of, key=lambda value: (weight_of[value], -value))

    def _intentional_hints(
        self, turn: _Turn, plan: Action | None
    ) -> tuple[list[_Candidate], list[Action]]:
        """Returns (qualifying hints scored with H, redundant hints)."""
        qualifying: list[_Candidate] = []
        redundant: list[Action] = []
        if turn.tokens == 0:
            return qualifying, redundant

        for hint in turn.legal:
            if not is_hint(hint):
                continue
            assert hint.pnr is not None
            hand = turn.hands[hint.pnr]
            before = turn.knowledge[hint.pnr]
            after = apply_hint(hint, hand, before)
            label = hint.num if hint.col is None else hint.col.display_name
            assert label is not None
            if not any(
                    identifies(hint, card) and new != old
                    for card, old, new in zip(hand, before, after)
            ):
                redundant.append(hint)
                self.redun_hints.append((label, hint.pnr, 0))
                continue

            # A hint to B is scored together with C's pending hint to B.
            pending = [plan] if plan is not None and hint.pnr == turn.b else []
            score_before = self._alignment(turn, hand, before, pending)
            score_after = self._alignment(turn, hand, after, pending + [hint])
            if score_after > score_before:
                gain = score_after - score_before
                qualifying.append(_Candidate(hint, hint_score=gain))
                self.valid_hints.append((label, hint.pnr, score_after))
        return qualifying, redundant

    def _alignment(
        self,
        turn: _Turn,
        hand: list[tuple[Color, int]],
        knowledge: list[list[list[int]]],
        pending: list[Action],
    ) -> float:
        """S(I_i, A^_i) for a partner's response to its ``pending`` hints."""
        touched = [any(identifies(hint, card) for hint in pending) for card in hand]
        return alignment_score(
            assign_goals(hand, turn.board, turn.trash),
            predict(knowledge, touched, turn.board),
            turn.hint_weights,
        )

    def _predicted_critical_discard(self, turn: _Turn) -> tuple[int, tuple[Color, int]] | None:
        """The first partner whose best discard candidate is a critical card (Section 6.11)."""
        partners = (turn.b, turn.c) if turn.b != turn.c else (turn.b,)
        for player in partners:
            knowledge = turn.knowledge[player]
            discards = [Action(DISCARD, cnr=i) for i in range(len(turn.hands[player]))]
            if not discards:
                continue
            best = max(
                discards,
                key=lambda a: pretend_discard(a, knowledge, turn.board, turn.trash)[1],
            )
            card = turn.hands[player][best.cnr]
            if is_critical(card, turn.board, turn.trash):
                return player, card
        return None

    def _safe_identifying_hints(
        self, turn: _Turn, plan: Action | None, player: int, card: tuple[Color, int]
    ) -> list[tuple[Action, float]]:
        """(hint, gain) for legal hints to ``player`` identifying ``card`` that add information and predict no misplay or harmful discard."""
        results: list[tuple[Action, float]] = []
        hand = turn.hands[player]
        before = turn.knowledge[player]
        pending = [plan] if plan is not None and player == turn.b else []
        for hint in turn.legal:
            if not (is_hint(hint) and hint.pnr == player and identifies(hint, card)):
                continue
            after = apply_hint(hint, hand, before)
            if not any(
                identifies(hint, c) and new != old
                for c, old, new in zip(hand, before, after)
            ):
                continue
            score_after = self._alignment(turn, hand, after, pending + [hint])
            if score_after == REJECTED:
                continue
            score_before = self._alignment(turn, hand, before, pending)
            gain = score_after - score_before if score_before != REJECTED else score_after
            results.append((hint, max(gain, 0.0)))
        return results

    def _mark_critical_saves(
        self, turn: _Turn, plan: Action | None, candidates: list[_Candidate]
    ) -> None:
        """First V9 stage: qualify and flag hints identifying the critical card a partner is predicted to discard."""
        if turn.tokens == 0:
            return
        prediction = self._predicted_critical_discard(turn)
        if prediction is None:
            return
        player, card = prediction
        for hint, gain in self._safe_identifying_hints(turn, plan, player, card):
            label = hint.num if hint.col is None else hint.col.display_name
            assert label is not None
            self.crit_hints.append((label, player, gain))
            existing = next((c for c in candidates if c.action == hint), None)
            if existing is not None:
                existing.crit_save = True
            else:
                # The pretend_v9 relaxation: a safe hint qualifies without a gain.
                candidates.append(_Candidate(hint, hint_score=gain, crit_save=True))

    def _critical_info_hint(self, turn: _Turn, plan: Action | None) -> Action | None:
        """Second V9 stage: the best safe hint identifying any critical card a partner holds."""
        best: tuple[float, Action] | None = None
        partners = (turn.b, turn.c) if turn.b != turn.c else (turn.b,)
        for player in partners:
            seen: set[tuple[Color, int]] = set()
            for card in turn.hands[player]:
                if card in seen or not is_critical(card, turn.board, turn.trash):
                    continue
                seen.add(card)
                for hint, gain in self._safe_identifying_hints(turn, plan, player, card):
                    label = hint.num if hint.col is None else hint.col.display_name
                    assert label is not None
                    self.crit_hints.append((label, player, gain))
                    if best is None or gain > best[0]:
                        best = (gain, hint)
        return best[1] if best is not None else None

    def _risky_play(self, turn: _Turn, fallback: Action) -> Action | None:
        """V17: a PLAY whose expected utility beats discarding ``fallback``, else None."""
        if turn.lives is None or turn.deck_size is None or turn.lives <= 1:
            return None
        own = turn.knowledge[turn.a]
        assert fallback.cnr is not None
        turns_left = turn.deck_size + len(turn.knowledge)
        life_cost = life_cost_v17(turn.lives, turns_left)
        q_discard = discard_utility_v17(own[fallback.cnr], turn.board, turn.tokens)
        best: tuple[float, float, int] | None = None
        for i, table in enumerate(own):
            q_play, p = play_utility_v17(table, turn.board, life_cost)
            if best is None or q_play > best[0]:
                best = (q_play, p, i)
        assert best is not None
        q_play, p, cnr = best
        self.explanation.append(
            [
                "Risky play (V17)",
                "Lives: {} | Turns left: {} | Life cost: {:.2f}".format(
                    turn.lives, turns_left, life_cost
                ),
                "Best play: card {} (p = {:.2f}, Q = {:.2f})".format(cnr, p, q_play),
                "Discard: card {} (Q = {:.2f})".format(fallback.cnr, q_discard),
            ]
        )
        # Ties keep the discard, as in risky_play_v17.
        if q_play > q_discard:
            return Action(PLAY, cnr=cnr)
        return None

    def _baseline_choice(self, turn: _Turn, top: list[_Candidate], plan: Action | None) -> Action:
        """Baseline priority sequence, restricted to ``top``."""
        own = turn.knowledge[turn.a]

        responses = [candidate for candidate in top if candidate.utility > 0]
        if responses:
            return max(responses, key=lambda candidate: candidate.utility).action

        discards = [c.action for c in top if c.action.action_type is DISCARD]
        useless = []
        for action in discards:
            assert action.cnr is not None
            possible = get_possible(own[action.cnr])
            if possible and discardable(possible, turn.board):
                useless.append(action)
        if useless:
            return random.choice(useless)

        # A hint protecting a predicted critical discard precedes other hints (V9).
        saves = [candidate for candidate in top if candidate.crit_save]
        if saves:
            best = max(candidate.hint_score for candidate in saves)
            return random.choice([c.action for c in saves if c.hint_score == best])

        hints = [candidate for candidate in top if is_hint(candidate.action)]
        if hints:
            best = max(candidate.hint_score for candidate in hints)
            return random.choice([c.action for c in hints if c.hint_score == best])

        # pretend_discard returns the negated expected loss.
        fallback = max(
            discards,
            key=lambda action: pretend_discard(action, own, turn.board, turn.trash)[1],
        )
        if self.risky_play:
            play = self._risky_play(turn, fallback)
            if play is not None:
                self.played_risky = True
                return play
        # Hint any critical card, only when tokens are plentiful (V19).
        if self.critical_card_hints and turn.tokens >= CRIT_INFO_MIN_TOKENS:
            hint = self._critical_info_hint(turn, plan)
            if hint is not None:
                self.explanation.append(["Critical card hint", str(hint)])
                return hint
        return fallback

    def _explain(self, candidates: list[_Candidate]) -> None:
        self.explanation.append(["Case", self.case])
        self.explanation.append(["Candidate"] + [str(c.action) for c in candidates])
        self.explanation.append(["Utility U"] + [c.utility for c in candidates])
        self.explanation.append(["Plan S"] + [c.plan for c in candidates])
        self.explanation.append(["Hint score H"] + [c.hint_score for c in candidates])
        self.explanation.append(["Critical save"] + [c.crit_save for c in candidates])
