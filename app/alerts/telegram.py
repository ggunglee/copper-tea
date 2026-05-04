from __future__ import annotations

import time

import requests
from requests import RequestException


class TelegramClient:
    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        connect_timeout: float = 10,
        read_timeout: float = 30,
        retries: int = 3,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.retries = max(1, retries)

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, message: str) -> bool:
        if not self.enabled:
            print(message)
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        last_error: RequestException | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    url,
                    json={"chat_id": self.chat_id, "text": message, "disable_web_page_preview": True},
                    timeout=(self.connect_timeout, self.read_timeout),
                )
                response.raise_for_status()
                return True
            except RequestException as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 * attempt, 8))
        print(f"Telegram send failed after {self.retries} attempts: {last_error}")
        return False
