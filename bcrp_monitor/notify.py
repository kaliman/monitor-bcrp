"""Telegram and Gmail notifiers."""

from __future__ import annotations

import io
import logging
import re
import smtplib
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage

from .config import Secrets
from .constants import (
    DEFAULT_PDF_NAME,
    SMTP_HOST,
    SMTP_PORT,
    TELEGRAM_API_BASE,
    TELEGRAM_CAPTION_LIMIT,
)
from .render import plain_of

log = logging.getLogger(__name__)


def _safe_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return f"HTTP {code}" if code else type(exc).__name__


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return cleaned or DEFAULT_PDF_NAME


class Telegram:
    def __init__(
        self,
        secrets: Secrets,
        timeout: int = 45,
        pdf_timeout: int = 120,
    ) -> None:
        self._token = secrets.telegram_bot_token
        self._chat_id = secrets.telegram_chat_id
        self._timeout = timeout
        self._pdf_timeout = pdf_timeout

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send_text(self, text: str) -> bool:
        if not self.enabled:
            return False
        data = urllib.parse.urlencode(
            {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "false",
            }
        ).encode()
        try:
            self._call("sendMessage", data, self._timeout)
        except Exception as exc:
            log.error("Telegram send failed (%s)", _safe_error(exc))
            return False
        log.info("Telegram: message sent")
        return True

    def send_pdf(self, pdf: bytes, filename: str, caption: str) -> bool:
        if not self.enabled:
            return False
        boundary = "----bcrp" + uuid.uuid4().hex
        body = io.BytesIO()

        def field(name: str, value: str) -> None:
            body.write(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}\r\n'.encode()
            )

        field("chat_id", self._chat_id)
        field("caption", caption[:TELEGRAM_CAPTION_LIMIT])
        body.write(
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="document"; filename="{_safe_filename(filename)}"\r\n'
            "Content-Type: application/pdf\r\n\r\n".encode()
        )
        body.write(pdf)
        body.write(f"\r\n--{boundary}--\r\n".encode())

        try:
            self._call(
                "sendDocument",
                body.getvalue(),
                self._pdf_timeout,
                content_type=f"multipart/form-data; boundary={boundary}",
            )
        except Exception as exc:
            log.error("Telegram PDF failed (%s)", _safe_error(exc))
            return False
        log.info("Telegram: PDF sent")
        return True

    def _call(
        self,
        method: str,
        data: bytes,
        timeout: int,
        content_type: str | None = None,
    ) -> None:
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/{method}"
        headers = {"Content-Type": content_type} if content_type else {}
        request = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()


class Gmail:
    def __init__(self, secrets: Secrets, timeout: int = 60) -> None:
        self._user = secrets.gmail_user
        self._password = secrets.gmail_app_password
        self._to = secrets.gmail_to or secrets.gmail_user
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._user and self._password)

    def send(
        self,
        subject: str,
        html: str,
        pdf: bytes | None = None,
        filename: str = DEFAULT_PDF_NAME,
    ) -> bool:
        if not self.enabled:
            return False
        message = EmailMessage()
        message["From"] = self._user
        message["To"] = self._to
        message["Subject"] = subject
        message.set_content(plain_of(html))
        message.add_alternative(
            "<html><body style='font-family:Segoe UI,Arial'>"
            f"{html}</body></html>",
            subtype="html",
        )
        if pdf:
            message.add_attachment(
                pdf,
                maintype="application",
                subtype="pdf",
                filename=_safe_filename(filename),
            )
        try:
            with smtplib.SMTP_SSL(
                SMTP_HOST, SMTP_PORT, timeout=self._timeout
            ) as smtp:
                smtp.login(self._user, self._password)
                smtp.send_message(message)
        except Exception as exc:
            log.error("Gmail send failed (%s)", type(exc).__name__)
            return False
        log.info("Gmail: message sent")
        return True
