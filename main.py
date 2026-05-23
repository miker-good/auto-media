import logging
import sys
from config import Config
from scheduler import Scheduler, pipeline


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("auto_media.log", encoding="utf-8")
        ]
    )


def main():
    setup_logging()
    config = Config()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # single run mode
        pipeline(config, config.db_path)
    else:
        # daemon mode
        scheduler = Scheduler(config, config.db_path)
        scheduler.setup()
        scheduler.start()


if __name__ == "__main__":
    main()
