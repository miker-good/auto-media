import pytest
from scheduler import Scheduler, pipeline


def test_scheduler_has_crawl_job():
    """Verify scheduler registers crawl job"""
    from config import Config
    cfg = Config()
    cfg.crawl_interval_hours = 6
    sched = Scheduler(cfg, db_path=":memory:")
    sched.setup()
    jobs = sched.scheduler.get_jobs()
    job_names = [j.name for j in jobs]
    assert "crawl_all" in job_names


def test_scheduler_has_publish_jobs():
    from config import Config
    cfg = Config()
    cfg.publish_hour_1 = 9
    cfg.publish_hour_2 = 17
    sched = Scheduler(cfg, db_path=":memory:")
    sched.setup()
    jobs = sched.scheduler.get_jobs()
    job_names = [j.name for j in jobs]
    assert "publish_slot_1" in job_names
    assert "publish_slot_2" in job_names
