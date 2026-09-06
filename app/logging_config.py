import logging
import sys


def setup_logging(level: str = "info", debug: bool = False):
    log_level = getattr(logging, level.upper(), logging.INFO)
    if debug:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("athena.log", encoding="utf-8"),
        ],
        force=True,
    )

    for noisy in (
        "uvicorn.access",
        "httpx",
        "chromadb",
        "faster_whisper",
        "sentence_transformers",
        "urllib3",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
