"""Separate DEMO worker; polls persistent state and never calls external APIs."""

import logging
import time

from sqlalchemy import select

from paperlab.config import get_settings
from paperlab.database import Base, SessionLocal, engine
from paperlab.demo import run_demo_cycle
from paperlab.models import Experiment


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s paperlab-worker %(message)s")
logger = logging.getLogger("paperlab.worker")


def run_once() -> int:
    db = SessionLocal()
    completed = 0
    try:
        experiments = db.scalars(select(Experiment).where(
            Experiment.mode == "DEMO", Experiment.status.in_(("running", "paused_entries")),
        ).with_for_update(skip_locked=True)).all()
        for experiment in experiments:
            try:
                result = run_demo_cycle(db, experiment)
                completed += 1
                logger.info("synthetic cycle recorded: experiment=%s cycle=%s", experiment.id, result.get("cycle_id"))
            except Exception as exc:
                db.rollback()
                logger.error("cycle failed safely: experiment=%s type=%s", experiment.id, type(exc).__name__)
        return completed
    finally:
        db.close()


def main():
    if engine.url.get_backend_name() == "sqlite":
        Base.metadata.create_all(engine)
    interval = max(10, get_settings().worker_interval_seconds)
    logger.info("worker started in DEMO mode; external calls disabled; interval=%s seconds", interval)
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
