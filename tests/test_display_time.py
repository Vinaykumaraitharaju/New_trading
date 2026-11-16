from datetime import datetime

from reaction_alpha.display_time import indian_time


def test_utc_observation_and_deadline_are_shown_in_india_time():
    assert indian_time("2026-11-16T03:51:41.000000+00:00") == "16 Nov 2026, 09:21:41 AM IST"
    assert indian_time("2026-11-16T04:30:11.145991Z") == "16 Nov 2026, 10:00:11 AM IST"
    assert indian_time("2026-11-16T10:00:11+05:30") == "16 Nov 2026, 10:00:11 AM IST"
    assert indian_time("2026-11-16T20:00:00Z") == "17 Nov 2026, 01:30:00 AM IST"
    assert indian_time(None) is None


def test_naive_server_observation_uses_writer_host_timezone():
    epoch = 1794801101
    assert indian_time(datetime.fromtimestamp(epoch)) == indian_time("2026-11-16T03:51:41Z")
