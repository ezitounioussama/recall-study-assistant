"""FSRS-5: the Free Spaced Repetition Scheduler.

A memory model, not a ladder of fixed intervals. Each card carries three
quantities:

  stability      S — days until the probability of recall falls to 90%
  difficulty     D — 1..10, how much this card resists this student
  retrievability R — the probability of recalling it right now, derived from
                     S and the time since the last review

Rating a card updates S and D; the next interval is the time until R falls to
the desired retention. Every formula below is the published FSRS-5 one with
its default weights; nothing is hand-tuned.

Pure. No clock, no database: `now` is always passed in, which is what makes
the whole thing testable without sleeping.

Reference: https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum


class Rating(IntEnum):
    AGAIN = 1  # forgot
    HARD = 2  # recalled, with real effort
    GOOD = 3  # recalled
    EASY = 4  # recalled instantly


class State(StrEnum):
    LEARNING = "learning"  # new card, still inside the learning steps
    REVIEW = "review"  # graduated; intervals come from the model
    RELEARNING = "relearning"  # lapsed from review, inside the relearning steps


# FSRS-5 default weights, w0..w18.
DEFAULT_WEIGHTS: tuple[float, ...] = (
    0.40255, 1.18385, 3.173, 15.69105,  # w0-3   initial stability per rating
    7.1949, 0.5345,  # w4-5   initial difficulty
    1.4604, 0.0046,  # w6-7   difficulty update and mean reversion
    1.54575, 0.1192, 1.01925,  # w8-10  stability after recall
    1.9395, 0.11, 0.29605, 2.2698,  # w11-14 stability after forgetting
    0.2315, 2.9898,  # w15-16 hard penalty, easy bonus
    0.51655, 0.6621,  # w17-18 same-day (short-term) stability
)

# R(t) = (1 + FACTOR * t / S) ** DECAY. FACTOR is chosen so that R(S) = 0.9
# exactly — that is what "stability" means.
DECAY = -0.5
FACTOR = 0.9 ** (1 / DECAY) - 1  # 19/81

MIN_DIFFICULTY, MAX_DIFFICULTY = 1.0, 10.0
MIN_STABILITY = 0.001


@dataclass(frozen=True)
class Memory:
    """Everything the scheduler knows about one card."""

    state: State = State.LEARNING
    step: int | None = 0
    stability: float | None = None
    difficulty: float | None = None
    due: dt.datetime | None = None
    last_review: dt.datetime | None = None


@dataclass(frozen=True)
class Scheduler:
    weights: tuple[float, ...] = DEFAULT_WEIGHTS
    desired_retention: float = 0.9
    learning_steps: tuple[dt.timedelta, ...] = (dt.timedelta(minutes=1), dt.timedelta(minutes=10))
    relearning_steps: tuple[dt.timedelta, ...] = (dt.timedelta(minutes=10),)
    maximum_interval_days: int = 36500

    # ---- the model ----------------------------------------------------------

    def retrievability(self, memory: Memory, now: dt.datetime) -> float:
        """Probability of recall at `now`. 1.0 for a card never reviewed."""
        if memory.stability is None or memory.last_review is None:
            return 1.0
        elapsed = max(0.0, (now - memory.last_review).total_seconds() / 86400)
        return (1 + FACTOR * elapsed / memory.stability) ** DECAY

    def next_interval(self, stability: float) -> int:
        """Whole days until R falls to the desired retention."""
        days = stability / FACTOR * (self.desired_retention ** (1 / DECAY) - 1)
        return int(min(max(round(days), 1), self.maximum_interval_days))

    def _initial_stability(self, rating: Rating) -> float:
        return max(self.weights[rating - 1], MIN_STABILITY)

    def _initial_difficulty(self, rating: Rating) -> float:
        w = self.weights
        return _clamp(w[4] - math.exp(w[5] * (rating - 1)) + 1)

    def _next_difficulty(self, difficulty: float, rating: Rating) -> float:
        w = self.weights
        delta = -w[6] * (rating - 3)
        # Linear damping: the same rating moves a hard card less than an easy one,
        # so difficulty approaches 10 rather than crossing it.
        damped = difficulty + delta * (MAX_DIFFICULTY - difficulty) / 9
        # Mean reversion towards the difficulty a brand-new "easy" card would
        # have, so a run of bad days does not brand a card forever.
        reverted = w[7] * self._initial_difficulty(Rating.EASY) + (1 - w[7]) * damped
        return _clamp(reverted)

    def _recall_stability(self, difficulty: float, stability: float, r: float, rating: Rating) -> float:
        w = self.weights
        hard_penalty = w[15] if rating == Rating.HARD else 1.0
        easy_bonus = w[16] if rating == Rating.EASY else 1.0
        growth = (
            math.exp(w[8])
            * (11 - difficulty)
            * stability ** (-w[9])
            * (math.exp(w[10] * (1 - r)) - 1)
            * hard_penalty
            * easy_bonus
        )
        return max(stability * (growth + 1), MIN_STABILITY)

    def _forget_stability(self, difficulty: float, stability: float, r: float) -> float:
        w = self.weights
        post_lapse = w[11] * difficulty ** (-w[12]) * ((stability + 1) ** w[13] - 1) * math.exp(w[14] * (1 - r))
        # Forgetting cannot leave a card more stable than it was.
        return max(min(post_lapse, stability), MIN_STABILITY)

    def _short_term_stability(self, stability: float, rating: Rating) -> float:
        """Reviews inside the same day: the learning steps, in practice."""
        w = self.weights
        return max(stability * math.exp(w[17] * (rating - 3 + w[18])), MIN_STABILITY)

    # ---- the state machine --------------------------------------------------

    def review(self, memory: Memory, rating: Rating, now: dt.datetime) -> Memory:
        """The card after being rated at `now`."""
        stability, difficulty = self._update_memory(memory, rating, now)
        base = replace(memory, stability=stability, difficulty=difficulty, last_review=now)

        if memory.state == State.LEARNING:
            return self._step(base, rating, now, self.learning_steps)
        if memory.state == State.RELEARNING:
            return self._step(base, rating, now, self.relearning_steps)

        # Review.
        if rating == Rating.AGAIN and self.relearning_steps:
            return replace(
                base, state=State.RELEARNING, step=0, due=now + self.relearning_steps[0]
            )
        return replace(base, state=State.REVIEW, step=None, due=now + self._interval(stability))

    def preview(self, memory: Memory, now: dt.datetime) -> dict[Rating, Memory]:
        """What each rating would do — for the four buttons under a card."""
        return {rating: self.review(memory, rating, now) for rating in Rating}

    def _update_memory(self, memory: Memory, rating: Rating, now: dt.datetime) -> tuple[float, float]:
        if memory.stability is None or memory.difficulty is None:
            return self._initial_stability(rating), self._initial_difficulty(rating)

        elapsed_days = (
            (now - memory.last_review).total_seconds() / 86400 if memory.last_review else 0.0
        )
        if elapsed_days < 1:
            stability = self._short_term_stability(memory.stability, rating)
        else:
            r = self.retrievability(memory, now)
            stability = (
                self._forget_stability(memory.difficulty, memory.stability, r)
                if rating == Rating.AGAIN
                else self._recall_stability(memory.difficulty, memory.stability, r, rating)
            )
        # Difficulty is updated after stability: the stability formulas take the
        # difficulty the card had going into this review.
        return stability, self._next_difficulty(memory.difficulty, rating)

    def _step(
        self, memory: Memory, rating: Rating, now: dt.datetime, steps: tuple[dt.timedelta, ...]
    ) -> Memory:
        """Walk the learning (or relearning) steps; graduate to Review at the end."""
        assert memory.stability is not None
        graduate = replace(memory, state=State.REVIEW, step=None, due=now + self._interval(memory.stability))

        if not steps:
            return graduate

        step = memory.step or 0
        if rating == Rating.AGAIN:
            return replace(memory, step=0, due=now + steps[0])
        if rating == Rating.HARD:
            # Hard does not advance. At the first step it waits a little longer
            # than Again would, without jumping to the next step.
            if step == 0 and len(steps) == 1:
                wait = steps[0] * 1.5
            elif step == 0:
                wait = (steps[0] + steps[1]) / 2
            else:
                wait = steps[min(step, len(steps) - 1)]
            return replace(memory, step=step, due=now + wait)
        if rating == Rating.GOOD:
            if step + 1 >= len(steps):
                return graduate
            return replace(memory, step=step + 1, due=now + steps[step + 1])
        return graduate  # EASY

    def _interval(self, stability: float) -> dt.timedelta:
        return dt.timedelta(days=self.next_interval(stability))


def _clamp(difficulty: float) -> float:
    return min(max(difficulty, MIN_DIFFICULTY), MAX_DIFFICULTY)
