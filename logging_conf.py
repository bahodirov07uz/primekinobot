from __future__ import annotations

import logging


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
