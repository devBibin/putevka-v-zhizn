import os
import logging

import httpx
from openai import OpenAI


logger = logging.getLogger(__name__)


def normalize_proxy_url(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.startswith("socks5h://"):
        return "socks5://" + value[len("socks5h://"):]
    return value


def make_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GPT_TOKEN")
    proxy = normalize_proxy_url(os.getenv("TELEGRAM_SOCKS5_PROXY"))
    if not api_key:
        logger.warning("OpenAI API key is not configured")
    logger.debug("Creating OpenAI client proxy_enabled=%s max_retries=%s", bool(proxy), os.getenv("OPENAI_MAX_RETRIES", "5"))
    http_client = httpx.Client(
        proxy=proxy if proxy else None,
        timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=300.0),
        limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
        verify=True,
    )
    return OpenAI(
        api_key=api_key,
        http_client=http_client,
        max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "5")),
    )
