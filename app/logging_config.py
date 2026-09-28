import logging
import sys


def setup_logging(level: str = "info", debug: bool = False, log_sql: bool = False):
    root_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=root_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("athena.log", encoding="utf-8"),
        ],
        force=True,
    )

    # App-specific loggers use DEBUG when debug mode is on; root stays at log_level.
    app_level = logging.DEBUG if debug else root_level
    logging.getLogger("app").setLevel(app_level)
    logging.getLogger("main").setLevel(app_level)

    # Pin noisy third-party libraries so they never inherit DEBUG from root.
    for noisy in (
        "aiosqlite",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "httpx",
        "httpcore",
        "asyncio",
        "watchfiles",
        "multipart",
        "urllib3",
        "hpack",
        "uvicorn.access",
        "chromadb",
        "faster_whisper",
        "sentence_transformers",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # SQL tracing: raise sqlalchemy.engine to INFO on demand via LOG_SQL=true.
    if log_sql:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
