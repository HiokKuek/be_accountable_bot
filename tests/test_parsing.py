from app.parsing import parse_done_count, parse_goals


def test_parse_done_count_accepts_zero_to_three():
    assert parse_done_count("/done 0") == 0
    assert parse_done_count("/done 2") == 2
    assert parse_done_count("/done 3") == 3


def test_parse_done_count_rejects_out_of_range():
    assert parse_done_count("/done 4") is None
    assert parse_done_count("/done nope") is None


def test_parse_goals_from_command_with_bullets():
    text = """/goals
- investment stuff
- intervals
- read"""
    assert parse_goals(text) == ["investment stuff", "intervals", "read"]


def test_parse_goals_from_checkins_format():
    text = """8/7 checkins:
- investment stuff
- intervals
- read!"""
    assert parse_goals(text) == ["investment stuff", "intervals", "read!"]


def test_parse_goals_requires_exactly_three_goals():
    assert parse_goals("""/goals
- one
- two""") is None
    assert parse_goals("""/goals
- one
- two
- three
- four""") is None
