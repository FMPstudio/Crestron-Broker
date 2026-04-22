from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class MatroxEndpoints:
    login: str = "/user/login"
    video_stream: str = "/device/settings/streams/video/0"
    video_manual: str = "/device/settings/streams/video/0/manual"
    audio_stream: str = "/device/settings/streams/audio/0"
    audio_manual: str = "/device/settings/streams/audio/0/manual"


class MatroxClient:
    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        timeout_seconds: float,
        retry_attempts: int,
        backoff_seconds: float,
        dry_run: bool,
    ) -> None:
        self.ip = ip
        self.username = username
        self.password = password
        self.retry_attempts = retry_attempts
        self.backoff_seconds = backoff_seconds
        self.dry_run = dry_run
        self.endpoints = MatroxEndpoints()
        self.log = logging.getLogger(f"matrox.{ip}")

        self.client = httpx.Client(
            base_url=f"https://{ip}",
            verify=False,
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def login(self) -> None:
        body = {
            "username": self.username,
            "password": self.password,
            "closeExistingSessions": False,
        }
        response = self._request("POST", self.endpoints.login, json=body)

        if response.status_code != 200:
            raise RuntimeError(f"Login failed on {self.ip}. Status={response.status_code}, body={response.text}")

        data = response.json()
        token = data.get("access_token")
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"

    def get_stream_snapshot(self) -> dict:
        video_stream = self._request("GET", self.endpoints.video_stream).json()
        audio_stream = self._request("GET", self.endpoints.audio_stream).json()
        video_manual = self._request("GET", self.endpoints.video_manual).json()
        audio_manual = self._request("GET", self.endpoints.audio_manual).json()
        return {
            "video_stream": video_stream,
            "audio_stream": audio_stream,
            "video_manual": video_manual,
            "audio_manual": audio_manual,
        }

    def apply_video_manual(self, payload: dict) -> None:
        self._request("POST", self.endpoints.video_manual, json=payload)

    def apply_audio_manual(self, payload: dict) -> None:
        self._request("POST", self.endpoints.audio_manual, json=payload)

    def apply_video_stream(self, payload: dict) -> None:
        self._request("POST", self.endpoints.video_stream, json=payload)

    def apply_audio_stream(self, payload: dict) -> None:
        self._request("POST", self.endpoints.audio_stream, json=payload)

    def _request(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        last_error: Exception | None = None

        if self.dry_run and method.upper() == "POST":
            self.log.info("DRY-RUN %s https://%s%s payload=%s", method, self.ip, path, json)
            return httpx.Response(status_code=200, request=httpx.Request(method, f"https://{self.ip}{path}"), json={"dry_run": True})

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.client.request(method, path, json=json)
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code} for {method} {path}: {response.text}")
                return response
            except Exception as exc:
                last_error = exc
                self.log.warning("Attempt %s/%s failed for %s %s: %s", attempt, self.retry_attempts, method, path, exc)
                if attempt < self.retry_attempts:
                    time.sleep(self.backoff_seconds)

        raise RuntimeError(f"Request failed for {method} {path} after retries: {last_error}")
