"""V16 (Cooperative Hints).

Subclass of the baseline full agent (SelfIntentionalPlayer, version 0).
Turn order is that version. Two extra hint decisions, both skipped when
``cooperative`` is false:

1. Giver. After the baseline picks its best legal hint, look at hints to
   the player two seats away that ``pretend`` rejects only because of a
   predicted-play collision. Any colliding card is a starter candidate:
   hinting its other attribute (rank if the blocked hint was color, color
   if it was rank) is a starter when that makes the original hint legal.
   Critical collisions (a 5, or the last unseen copy of 1-4, counting
   trash and copies visible in other hands) only get a ranking bonus among
   candidates. Starters score 0.5 below the hint they set up, so a clean
   intentional hint of the same strength wins.

   Before giving a starter, simulate the next player's (B's) turn as if the
   starter had just been given — the same early stages V13 uses. If B would
   resolve to a certainly-playable play or a certainly-useless discard (both
   before B's hint-giving stage), or the starter would leave B with no hint
   token, skip the starter and keep the baseline choice: B would not reach
   the follow-up. Otherwise give the starter.
2. Next player. If a legal follow-up is pending, complete it before any
   uncertain ``received_hint`` play or discard. A certainly-playable play
   or certainly-useless discard still happens first. Without a pending
   follow-up, receiving a hint is the baseline.

Where the baseline pieces live (unchanged):
- Scoring and legality: ``utils.pretend``, called from
  ``SelfIntentionalPlayer.give_intentional_hint``.
- Predicted-play rejection: ``pretend`` returns False when ``whattodo``
  says PLAY on a card whose true intent is not PLAY.
- Other players' mental state: ``knowledge[player_id][slot]``, the
  color-by-rank count matrix maintained by ``HanasimGame._update_knowledge``.
  The giver also sees true cards in ``hands[player_id]``.
"""

from players.self_intentional import SelfIntentionalPlayer
from utils import (
    Action,
    Color,
    Intent,
    MAX_HINT_TOKENS,
    discardable,
    f,
    get_possible,
    hint_color,
    hint_rank,
    playable,
    pretend,
    whattodo,
)

# Below a clean hint with the same pretend score, above a clean hint
# whose score is at least 1 lower (scores are integers).
STARTER_PENALTY = 0.5
# Ranking-only: prefer a critical collision when two starters share a score.
# Not added to the score compared against the baseline hint.
CRITICAL_BONUS = 0.25

_HINTS = {Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER}


class _Episode:
    def __init__(self, giver, follower, target, followup):
        self.giver = giver
        self.follower = follower
        self.target = target
        self.followup = followup
        self.phase = "await_follower"
        self.overwritten = False
        self.completed = False


class CooperativeHintPlayer(SelfIntentionalPlayer):
    def __init__(self, name, pnr, cooperative=True):
        super().__init__(name, pnr, version=0)
        self.cooperative = cooperative
        self.starters_given = 0
        self.starters_completed = 0
        self.starter_misplays = 0
        self._open: list[_Episode] = []
        self._last_lives = 3

    def reset(self) -> None:
        super().reset()
        self.starters_given = 0
        self.starters_completed = 0
        self.starter_misplays = 0
        self._open = []
        self._last_lives = 3

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints, lives, deck_size
    ):
        if not self.cooperative:
            return super().get_action(
                nr, hands, knowledge, trash, played, board, valid_actions, hints, lives, deck_size
            )

        num_players = len(knowledge)
        possible = []
        result = None
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - nr])))
        action_buf = []
        self.valid_hints = []
        self.redun_hints = []

        follow = None
        follow_ready = False
        if hints > 0 and num_players == 3:
            follow = self._pending_followup()
            follow_ready = (
                follow is not None
                and follow in valid_actions
                and self._followup_ok(
                    follow, nr, hands, knowledge, trash, board
                )
            )

        if follow_ready:
            # Certain play/discard, then the follow-up, then uncertain hint
            # interpretation. Consume got_hint if the follow-up or a certain
            # action already filled the turn, so it does not persist.
            if not result:
                result = self.play_or_discard(
                    nr, knowledge, board, hints, possible, result
                )
            if not result:
                result = follow
            if self.got_hint:
                if not result:
                    result = self.received_hint(
                        nr, knowledge, board, hints, result, action_buf
                    )
                else:
                    self.got_hint = None
        else:
            if self.got_hint:
                result = self.received_hint(
                    nr, knowledge, board, hints, result, action_buf
                )
            if not result:
                result = self.play_or_discard(
                    nr, knowledge, board, hints, possible, result
                )

        redundant_hints = []
        if not result:
            result, redundant_hints = self._give_intentional(
                nr, hands, knowledge, trash, board, hints, num_players, result
            )
            if hints > 0 and num_players == 3:
                starter = self._chosen_starter(
                    nr, hands, knowledge, trash, board, num_players, hints, result
                )
                if starter is not None and starter in valid_actions:
                    result = starter

        if hints == MAX_HINT_TOKENS and not result:
            if redundant_hints:
                result = self.give_redundant_hint(redundant_hints)
            else:
                result = self.give_random_hint(valid_actions)

        scores = self.discard_card(nr, knowledge, trash, board)
        if result:
            assert result in valid_actions
            return result
        assert scores[0][0] in valid_actions
        return scores[0][0]

    def _give_intentional(
        self, nr, hands, knowledge, trash, board, hints, num_players, result
    ):
        """Baseline intentional hint. Overridden by V21 to use V15 scoring."""
        return self.give_intentional_hint(
            nr, hands, knowledge, trash, board, hints, num_players, result
        )

    def _score_hint(self, hint, knowledge, intentions, hand, board, trash, hints):
        """Score/legality for one hint. Overridden by V21 to use pretend_v15."""
        return pretend(hint, knowledge, intentions, hand, board, trash)

    def inform(self, action, player, game):
        super().inform(action, player, game)
        if not self.cooperative:
            return
        lives_now = game._obs.lives_remaining
        self._resolve_open(action, player, lives_now)
        if (
            action.action_type in _HINTS
            and action.pnr is not None
            and len(game.knowledge) == 3
        ):
            self._maybe_open(action, player, game)
        self._last_lives = lives_now

    def _pending_followup(self):
        for ep in self._open:
            if ep.phase == "await_follower" and ep.follower == self.pnr:
                return ep.followup
        return None

    def _followup_ok(self, follow, nr, hands, knowledge, trash, board):
        target = follow.pnr
        if target is None or target == nr or not hands[target]:
            return False
        intentions = self._create_intents(hands[target], board, trash)
        hint = _action_to_hint(follow)
        # Follow-up legality uses the same scorer as intentional hints.
        isvalid, _, _ = self._score_hint(
            hint, knowledge[target], intentions, hands[target], board, trash, 1
        )
        return isvalid

    def _chosen_starter(
        self, actor, hands, knowledge, trash, board, num_players, hints, baseline
    ):
        """Starter to give instead of ``baseline``, or None."""
        base_action, base_score, starter = self._decide(
            actor, hands, knowledge, trash, board, num_players, hints
        )
        if baseline is not None and baseline.action_type in _HINTS:
            if base_action != baseline:
                # Enumeration drifted from give_intentional_hint. Do not override.
                return None
        elif baseline is None and base_action is not None:
            return None
        if starter is None:
            return None
        starter_score, starter_action, _follow = starter
        if base_action is not None and starter_action == base_action:
            return None
        if base_score is not None and base_score > starter_score:
            return None
        return starter_action

    def _resolve_open(self, action, player, lives_now):
        still = []
        for ep in self._open:
            if ep.phase == "await_follower" and player == ep.follower:
                if action == ep.followup:
                    if self.pnr == ep.giver:
                        self.starters_completed += 1
                    continue
                ep.phase = "await_target"
                if action.action_type in _HINTS and action.pnr == ep.target:
                    ep.overwritten = True
                still.append(ep)
            elif ep.phase == "await_target" and player == ep.target:
                bombed = (
                    action.action_type == Action.ActionType.PLAY
                    and not ep.overwritten
                    and lives_now < self._last_lives
                )
                if bombed and self.pnr == ep.giver:
                    self.starter_misplays += 1
                continue
            else:
                still.append(ep)
        self._open = still

    def _maybe_open(self, action, player, game):
        hands, knowledge, board, trash = _actor_view(game, player)
        # inform() runs after the hint spent a token, so hint_tokens is
        # already tokens_after; pass hints+1 so _decide subtracts one.
        hints_before = game._obs.hint_tokens + 1
        base_action, base_score, starter = self._decide(
            player, hands, knowledge, trash, board, 3, hints_before
        )
        if starter is None:
            return
        starter_score, starter_action, followup = starter
        if action != starter_action:
            return
        if base_action is not None and starter_action == base_action:
            return
        if base_score is not None and base_score > starter_score:
            return
        if self.pnr == player:
            self.starters_given += 1
        self._open.append(
            _Episode(
                giver=player,
                follower=(player + 1) % 3,
                target=(player + 2) % 3,
                followup=followup,
            )
        )

    def _follower_reaches_hints(self, follower, knowledge, board, tokens_after):
        """True iff B can reach the hint stage with a token to spend.

        Mirrors V13 stages 1–3 of ``_next_player_penalty_v13``: a certainly
        playable card, or (when not at max tokens) a certainly useless card,
        both resolve before B would give the follow-up hint, and B needs a
        token left after the starter to give it at all.
        """
        if tokens_after <= 0:
            return False
        b_possible = [get_possible(k) for k in knowledge[follower]]
        for p in b_possible:
            if playable(p, board):
                return False
        if tokens_after < MAX_HINT_TOKENS:
            for p in b_possible:
                if discardable(p, board):
                    return False
        return True

    def _decide(self, actor, hands, knowledge, trash, board, num_players, hints):
        """Return (baseline_action, baseline_score, starter_or_none).

        ``starter_or_none`` is (score, starter_action, followup_action).
        Baseline enumeration matches ``give_intentional_hint`` for 3 players:
        partner order, then colors, then ranks, stable sort by score.

        A candidate starter is dropped when the next player would play or
        discard with certainty before reaching their hint-giving stage.
        """
        if num_players != 3:
            return None, None, None
        follower = (actor + 1) % 3
        target = (actor + 2) % 3
        intents = {
            follower: self._create_intents(hands[follower], board, trash),
            target: self._create_intents(hands[target], board, trash),
        }

        valid = []
        for hintee in range(num_players):
            if hintee == actor:
                continue
            for hint in _all_hints():
                isvalid, score, _ = self._score_hint(
                    hint,
                    knowledge[hintee],
                    intents[hintee],
                    hands[hintee],
                    board,
                    trash,
                    hints,
                )
                if isvalid:
                    valid.append((hint, score, hintee))
        base_action, base_score = None, None
        if valid:
            valid.sort(key=lambda x: x[1], reverse=True)
            base_action = _as_action(valid[0][0], valid[0][2])
            base_score = valid[0][1]

        best = None
        best_rank = None
        hand = hands[target]
        know = knowledge[target]
        intentions = intents[target]
        for hint in _all_hints():
            scan = _scan(hint, know, intentions, hand, board)
            if not scan["only_play"]:
                continue
            for slot in scan["play_ix"]:
                other = _other_attribute(hint, hand[slot])
                updated = _apply_hint(know, hand, other)
                isvalid, score, _ = self._score_hint(
                    hint, updated, intentions, hand, board, trash, hints
                )
                if not isvalid:
                    continue
                starter_score = score - STARTER_PENALTY
                rank = starter_score
                if _is_critical(
                    hand[slot], board, trash, _other_visible_cards(hands, target, slot)
                ):
                    rank += CRITICAL_BONUS
                if best is None or rank > best_rank:
                    best_rank = rank
                    best = (
                        starter_score,
                        _as_action(other, target),
                        _as_action(hint, target),
                    )
        if best is not None and not self._follower_reaches_hints(
            follower, knowledge, board, hints - 1
        ):
            best = None
        return base_action, base_score, best


def _all_hints():
    hints = [(Action.ActionType.HINT_COLOR, c) for c in Color]
    hints.extend((Action.ActionType.HINT_NUMBER, r) for r in range(1, 6))
    return hints


def _as_action(hint, hintee):
    kind, value = hint
    if kind is Action.ActionType.HINT_COLOR:
        return Action(Action.ActionType.HINT_COLOR, pnr=hintee, col=value)
    return Action(Action.ActionType.HINT_NUMBER, pnr=hintee, num=value)


def _action_to_hint(action):
    if action.action_type is Action.ActionType.HINT_COLOR:
        return (Action.ActionType.HINT_COLOR, action.col)
    return (Action.ActionType.HINT_NUMBER, action.num)


def _other_attribute(hint, card):
    """The attribute the blocked hint did not name."""
    kind, _value = hint
    col, num = card
    if kind is Action.ActionType.HINT_COLOR:
        return (Action.ActionType.HINT_NUMBER, num)
    return (Action.ActionType.HINT_COLOR, col)


def _apply_hint(knowledge, hand, hint):
    kind, value = hint
    updated = []
    for i, (col, num) in enumerate(hand):
        if kind is Action.ActionType.HINT_COLOR:
            updated.append(hint_color(knowledge[i], value, value == col))
        else:
            updated.append(hint_rank(knowledge[i], value, value == num))
    return updated


def _other_visible_cards(hands, target, slot):
    """Cards A can see except the colliding slot itself."""
    cards = []
    for pid, hand in enumerate(hands):
        for i, card in enumerate(hand):
            if pid == target and i == slot:
                continue
            cards.append(card)
    return cards


def _is_critical(card, board, trash, other_cards):
    """Last remaining copy A can account for, still needed by a firework.

    Counts copies in the trash and in every visible hand other than this
    slot. A's own hand is hidden, so copies there are not counted.
    """
    col, num = card
    if board[col][1] >= num:
        return False
    accounted = sum(1 for c, r in trash if c == col and r == num)
    accounted += sum(1 for c, r in other_cards if c == col and r == num)
    if num == 5:
        return True
    if num == 1 and accounted == 2:
        return True
    if num in (2, 3, 4) and accounted == 1:
        return True
    return False


def _scan(hint, knowledge, intentions, hand, board):
    """pretend's rejection, without stopping at the first collision.

    ``only_play`` means the hint touches a card, adds information, would
    have an aligned play or discard if the bad plays were ignored, and the
    only rejections are predicted-play collisions.
    """
    kind, value = hint
    positive = []
    newknowledge = []
    haspositive = False
    change = False
    for i, (col, num) in enumerate(hand):
        if kind is Action.ActionType.HINT_COLOR:
            pointed = value == col
            updated = hint_color(knowledge[i], value, pointed)
        else:
            pointed = value == num
            updated = hint_rank(knowledge[i], value, pointed)
        positive.append(pointed)
        newknowledge.append(updated)
        if pointed:
            haspositive = True
            if updated != knowledge[i]:
                change = True
    empty = {
        "only_play": False,
        "play_ix": [],
    }
    if not haspositive or not change:
        return empty

    play_ix = []
    discard_ix = []
    aligned = False
    for i, (intent, k, pointed) in enumerate(zip(intentions, newknowledge, positive)):
        predicted = whattodo(k, pointed, board, None)
        if predicted == Action.ActionType.PLAY and intent != Intent.PLAY:
            play_ix.append(i)
        elif predicted == Action.ActionType.DISCARD and intent not in {
            Intent.DISCARD,
            Intent.CAN_DISCARD,
        }:
            discard_ix.append(i)
        elif predicted == Action.ActionType.PLAY and intent == Intent.PLAY:
            aligned = True
        elif predicted == Action.ActionType.DISCARD and intent in {
            Intent.DISCARD,
            Intent.CAN_DISCARD,
        }:
            aligned = True
    return {
        "only_play": bool(play_ix) and not discard_ix and aligned,
        "play_ix": play_ix,
    }


def _actor_view(game, actor):
    """Hands as ``actor`` saw them on their turn: own hand hidden."""
    cmap = game.hanasim_colour_map
    obs = game._obs
    hands = []
    for i, hand in enumerate(obs.hands):
        if i == actor:
            hands.append([])
        else:
            hands.append([(cmap[color], rank) for color, rank in hand])
    board = game._convert_board(obs.fireworks)
    trash = game._convert_trash(obs.discards)
    return hands, game.knowledge, board, trash
