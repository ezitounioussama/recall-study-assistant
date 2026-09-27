"""The trust report's arithmetic. The report is only as honest as these functions."""

from evaluation.metrics import GradeResult, QuestionResult, Report


def q(covered=True, sources=1, grounded=True, answer="ATP [1]", raw=None, citations=(1,), expect=("atp",)):
    return QuestionResult("q", covered, list(expect), sources, grounded, answer, raw or answer, list(citations), 1.0)


def test_an_invented_citation_is_one_that_points_past_the_passages():
    assert q(sources=1, raw="ATP [1] and [3]").invented_citations == [3]
    assert q(sources=2, raw="ATP [1] and [2]").invented_citations == []


def test_the_expected_fact_is_matched_case_insensitively():
    assert q(answer="They make ATP.").mentions_expected
    assert not q(answer="They make glucose.").mentions_expected


def test_refusals_are_counted_separately_for_covered_and_uncovered_questions():
    report = Report(questions=[
        q(covered=False, sources=0, grounded=False),
        q(covered=False, sources=1, grounded=False),
        q(covered=True, grounded=False),
        q(covered=True),
    ])
    s = report.summary()["refusal"]
    assert s["off_topic_refused"] == {"n": 2, "of": 2, "rate": 1.0}
    assert s["off_topic_refused_without_model"]["n"] == 1
    assert s["covered_wrongly_refused"] == {"n": 1, "of": 2, "rate": 0.5}


def test_a_wrong_answer_graded_correct_is_the_dangerous_error():
    report = Report(grades=[
        GradeResult("q", "a", "incorrect", "correct", 3, 1.0),
        GradeResult("q", "a", "incorrect", "partial", 2, 1.0),
        GradeResult("q", "a", "correct", "correct", 3, 1.0),
    ])
    g = report.summary()["grader"]
    assert g["exact_verdict"]["n"] == 1
    assert g["wrong_answer_graded_correct"]["n"] == 1
    assert g["confusion"]["incorrect"]["correct"] == 1


def test_an_empty_report_does_not_divide_by_zero():
    s = Report().summary()
    assert s["grader"]["exact_verdict"]["rate"] is None
    assert s["latency_seconds"]["chat_median"] is None
