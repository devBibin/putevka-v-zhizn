import logging
import logging.config
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.getenv("AI_LOG_DIR", BASE_DIR / "logs"))


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    ai_level = os.getenv("AI_LOG_LEVEL", level).upper()
    http_level = os.getenv("AI_HTTP_LOG_LEVEL", "WARNING").upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(levelname)s %(asctime)s %(name)s:%(lineno)d %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": level,
                    "formatter": "standard",
                },
                "file_info": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": ai_level,
                    "filename": str(LOG_DIR / "ai_service.log"),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                    "formatter": "standard",
                    "encoding": "utf-8",
                },
                "file_error": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "ERROR",
                    "filename": str(LOG_DIR / "ai_service_errors.log"),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 10,
                    "formatter": "standard",
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "ai_service": {
                    "handlers": ["console", "file_info", "file_error"],
                    "level": ai_level,
                    "propagate": False,
                },
                "httpx": {
                    "handlers": ["console", "file_info", "file_error"],
                    "level": http_level,
                    "propagate": False,
                },
                "openai": {
                    "handlers": ["console", "file_info", "file_error"],
                    "level": os.getenv("OPENAI_LOG_LEVEL", "WARNING").upper(),
                    "propagate": False,
                },
            },
            "root": {
                "handlers": ["console", "file_info", "file_error"],
                "level": level,
            },
        }
    )
