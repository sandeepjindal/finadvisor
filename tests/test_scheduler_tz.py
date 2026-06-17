from types import SimpleNamespace

from scheduler.jobs import build_scheduler, parse_digest_time


def _cfg():
    return SimpleNamespace(market_tz="America/New_York", digest_time="08:30")


def test_parse_digest_time():
    assert parse_digest_time("08:30") == (8, 30)
    assert parse_digest_time("17:05") == (17, 5)


def test_build_scheduler_registers_jobs_with_tz():
    sched = build_scheduler(
        _cfg(),
        digest_cb=lambda: None,
        crawl_cb=lambda: None,
        maintenance_cb=lambda: None,
    )
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"crawl", "digest", "maintenance"}
    assert str(jobs["digest"].trigger.timezone) == "America/New_York"
    assert not sched.running


def test_build_scheduler_optional_jobs():
    sched = build_scheduler(_cfg(), digest_cb=lambda: None)
    assert {j.id for j in sched.get_jobs()} == {"digest"}
