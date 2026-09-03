"""The scheduler's properties.

Not "does it return a number" — the shape of the model: retrievability decays
the way stability says it should, forgetting shrinks stability, an easy card
waits longer than a hard one, and the learning steps graduate.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.fsrs import DECAY, FACTOR, Memory, Rating, Scheduler, State

NOW = dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.timezone.utc)
DAY = dt.timedelta(days=1)


@pytest.fixture
def scheduler():
    return Scheduler()


def reviewed_card(scheduler, *ratings, start=NOW, gap=DAY):
    """Drive a fresh card through a sequence of ratings one gap apart."""
    memory = Memory()
    when = start
    for rating in ratings:
        memory = scheduler.review(memory, rating, when)
        when = when + gap
    return memory, when


class TestRetrievability:
    def test_a_new_card_is_certain(self, scheduler):
        assert scheduler.retrievability(Memory(), NOW) == 1.0

    def test_right_after_review_it_is_one(self, scheduler):
        memory = Memory(stability=10, difficulty=5, last_review=NOW)
        assert scheduler.retrievability(memory, NOW) == pytest.approx(1.0)

    def test_after_one_stability_it_is_ninety_percent(self, scheduler):
        """This is the definition of stability."""
        memory = Memory(stability=7, difficulty=5, last_review=NOW)
        assert scheduler.retrievability(memory, NOW + 7 * DAY) == pytest.approx(0.9)

    def test_it_only_decreases(self, scheduler):
        memory = Memory(stability=3, difficulty=5, last_review=NOW)
        values = [scheduler.retrievability(memory, NOW + n * DAY) for n in range(30)]
        assert values == sorted(values, reverse=True)

    def test_the_curve_is_the_published_one(self):
        assert FACTOR == pytest.approx(19 / 81)
        assert DECAY == -0.5


class TestIntervals:
    def test_interval_at_ninety_percent_retention_equals_stability(self, scheduler):
        for stability in (1, 5, 30, 365):
            assert scheduler.next_interval(stability) == stability

    def test_lower_retention_target_means_longer_waits(self):
        relaxed = Scheduler(desired_retention=0.8)
        strict = Scheduler(desired_retention=0.95)
        assert relaxed.next_interval(10) > Scheduler().next_interval(10) > strict.next_interval(10)

    def test_never_shorter_than_a_day_nor_longer_than_the_cap(self):
        s = Scheduler(maximum_interval_days=100)
        assert s.next_interval(0.001) == 1
        assert s.next_interval(10_000) == 100


class TestInitialMemory:
    def test_stability_rises_with_the_rating(self, scheduler):
        stabilities = [scheduler.review(Memory(), r, NOW).stability for r in Rating]
        assert stabilities == sorted(stabilities)

    def test_difficulty_falls_with_the_rating(self, scheduler):
        difficulties = [scheduler.review(Memory(), r, NOW).difficulty for r in Rating]
        assert difficulties == sorted(difficulties, reverse=True)
        assert all(1 <= d <= 10 for d in difficulties)


class TestReviewState:
    @pytest.fixture
    def review_card(self, scheduler):
        memory, when = reviewed_card(scheduler, Rating.GOOD, Rating.GOOD)
        assert memory.state == State.REVIEW
        return memory, when + 5 * DAY

    def test_recall_grows_stability(self, scheduler, review_card):
        memory, now = review_card
        after = scheduler.review(memory, Rating.GOOD, now)
        assert after.stability > memory.stability

    def test_forgetting_shrinks_stability_and_enters_relearning(self, scheduler, review_card):
        memory, now = review_card
        after = scheduler.review(memory, Rating.AGAIN, now)
        assert after.stability < memory.stability
        assert after.state == State.RELEARNING
        assert after.due == now + dt.timedelta(minutes=10)

    def test_easy_waits_longer_than_good_longer_than_hard(self, scheduler, review_card):
        memory, now = review_card
        preview = scheduler.preview(memory, now)
        assert preview[Rating.AGAIN].due < preview[Rating.HARD].due
        assert preview[Rating.HARD].due <= preview[Rating.GOOD].due < preview[Rating.EASY].due

    def test_forgetting_raises_difficulty_and_recall_lowers_it(self, scheduler, review_card):
        memory, now = review_card
        assert scheduler.review(memory, Rating.AGAIN, now).difficulty > memory.difficulty
        assert scheduler.review(memory, Rating.EASY, now).difficulty < memory.difficulty

    def test_difficulty_stays_in_range_under_abuse(self, scheduler):
        memory = Memory()
        when = NOW
        for _ in range(50):
            memory = scheduler.review(memory, Rating.AGAIN, when)
            when += DAY
        assert 1 <= memory.difficulty <= 10
        for _ in range(50):
            memory = scheduler.review(memory, Rating.EASY, when)
            when += 400 * DAY
        assert 1 <= memory.difficulty <= 10

    def test_a_long_overdue_card_that_is_recalled_gains_more(self, scheduler, review_card):
        """Recalling something you were likely to have forgotten is strong evidence."""
        memory, now = review_card
        on_time = scheduler.review(memory, Rating.GOOD, now)
        late = scheduler.review(memory, Rating.GOOD, now + 60 * DAY)
        assert late.stability > on_time.stability


class TestLearningSteps:
    def test_a_new_card_starts_in_learning(self):
        assert Memory().state == State.LEARNING

    def test_again_repeats_the_first_step(self, scheduler):
        after = scheduler.review(Memory(), Rating.AGAIN, NOW)
        assert after.state == State.LEARNING
        assert after.step == 0
        assert after.due == NOW + dt.timedelta(minutes=1)

    def test_good_walks_the_steps_then_graduates(self, scheduler):
        first = scheduler.review(Memory(), Rating.GOOD, NOW)
        assert first.state == State.LEARNING
        assert first.step == 1
        assert first.due == NOW + dt.timedelta(minutes=10)

        second = scheduler.review(first, Rating.GOOD, first.due)
        assert second.state == State.REVIEW
        assert second.step is None
        assert second.due >= first.due + DAY

    def test_easy_graduates_immediately(self, scheduler):
        after = scheduler.review(Memory(), Rating.EASY, NOW)
        assert after.state == State.REVIEW
        assert after.due - NOW >= DAY

    def test_hard_at_the_first_step_waits_between_the_two_steps(self, scheduler):
        after = scheduler.review(Memory(), Rating.HARD, NOW)
        assert after.step == 0
        assert after.due == NOW + dt.timedelta(minutes=5, seconds=30)

    def test_relearning_graduates_back_to_review(self, scheduler):
        memory, when = reviewed_card(scheduler, Rating.GOOD, Rating.GOOD)
        lapsed = scheduler.review(memory, Rating.AGAIN, when + 3 * DAY)
        assert lapsed.state == State.RELEARNING
        recovered = scheduler.review(lapsed, Rating.GOOD, lapsed.due)
        assert recovered.state == State.REVIEW

    def test_no_learning_steps_means_straight_to_review(self):
        scheduler = Scheduler(learning_steps=())
        assert scheduler.review(Memory(), Rating.GOOD, NOW).state == State.REVIEW

    def test_same_day_reviews_use_the_short_term_formula(self, scheduler):
        first = scheduler.review(Memory(), Rating.GOOD, NOW)
        later_today = scheduler.review(first, Rating.GOOD, NOW + dt.timedelta(minutes=10))
        assert later_today.stability > first.stability
