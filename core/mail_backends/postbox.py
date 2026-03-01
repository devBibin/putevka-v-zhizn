import base64
import json
import logging
from typing import Iterable, Optional

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

class PostboxEmailBackend(BaseEmailBackend):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.endpoint = getattr(settings, "POSTBOX_ENDPOINT", "https://postbox.cloud.yandex.net/v2/email/outbound-emails")
        self.region = getattr(settings, "POSTBOX_REGION", "ru-central1")
        self.service = getattr(settings, "POSTBOX_SERVICE", "ses")
        self.access_key = getattr(settings, "POSTBOX_ACCESS_KEY_ID", None)
        self.secret_key = getattr(settings, "POSTBOX_SECRET_ACCESS_KEY", None)

        if not self.access_key or not self.secret_key:
            raise RuntimeError("POSTBOX_ACCESS_KEY_ID / POSTBOX_SECRET_ACCESS_KEY are not set")

        try:
            from botocore.auth import SigV4Auth
            from botocore.awsrequest import AWSRequest
            from botocore.credentials import Credentials
        except Exception as e:
            raise RuntimeError("Install botocore: pip install botocore") from e

        self._SigV4Auth = SigV4Auth
        self._AWSRequest = AWSRequest
        self._Credentials = Credentials

        self._session = requests.Session()

    def send_messages(self, email_messages: Iterable) -> int:
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send_one(message)
                sent += 1
            except Exception:
                if self.fail_silently:
                    logger.exception("Postbox send failed (silenced)")
                else:
                    raise
        return sent

    def _send_one(self, msg) -> None:
        from_email = msg.from_email or settings.DEFAULT_FROM_EMAIL
        to_addrs = list(getattr(msg, "to", []) or [])
        cc_addrs = list(getattr(msg, "cc", []) or [])
        bcc_addrs = list(getattr(msg, "bcc", []) or [])

        mime = msg.message()
        if "From" not in mime:
            mime["From"] = from_email
        if "To" not in mime and to_addrs:
            mime["To"] = ", ".join(to_addrs)
        if "Cc" not in mime and cc_addrs:
            mime["Cc"] = ", ".join(cc_addrs)

        raw_bytes = mime.as_bytes()  # RFC822 bytes
        raw_b64 = base64.b64encode(raw_bytes).decode("ascii")

        payload = {
            "FromEmailAddress": from_email,
            "Destination": {
                "ToAddresses": to_addrs,
                "CcAddresses": cc_addrs,
                "BccAddresses": bcc_addrs,
            },
            "Content": {
                "Raw": {
                    "Data": raw_b64
                }
            },
        }

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Host": "postbox.cloud.yandex.net",
        }

        signed_headers = self._sign_headers("POST", self.endpoint, headers, body)

        resp = self._session.post(
            self.endpoint,
            data=body,
            headers=signed_headers,
            timeout=20,
        )

        if resp.status_code >= 400:
            raise RuntimeError(f"Postbox error {resp.status_code}: {resp.text}")

    def _sign_headers(self, method: str, url: str, headers: dict, body: bytes) -> dict:
        creds = self._Credentials(self.access_key, self.secret_key)
        req = self._AWSRequest(method=method, url=url, data=body, headers=headers)
        self._SigV4Auth(creds, self.service, self.region).add_auth(req)
        return dict(req.headers)