import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


def normalize_telegram_proxy_url(raw_proxy_url: str | None) -> str | None:
    proxy_url = (raw_proxy_url or "").strip()
    if not proxy_url:
        return None

    if "://" in proxy_url:
        return proxy_url

    parts = proxy_url.split(":")
    scheme = parts[0].lower()
    if scheme not in {"socks5", "socks5h"}:
        return proxy_url

    if len(parts) == 3:
        _, host, port = parts
        return f"socks5h://{host}:{port}"

    if len(parts) == 4:
        _, host, port, password = parts
        return f"socks5h://:{quote(password, safe='')}@{host}:{port}"

    if len(parts) == 5:
        _, host, port, username, password = parts
        return (
            f"socks5h://{quote(username, safe='')}:"
            f"{quote(password, safe='')}@{host}:{port}"
        )

    logger.warning("Telegram proxy format is not recognized: %s", proxy_url)
    return proxy_url
