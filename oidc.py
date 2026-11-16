from urllib.parse import urlencode
from dataclasses import dataclass
from config import OIDCConfig
import secrets
import threading
import time
import discord


@dataclass
class AuthRequest:
    url: str
    state: str
    nonce: str
    creation_time: int
    mc_username: str
    is_legit: bool
    dc_id: int
    dc_name: str


class OIDCManager:
    def __init__(self, config: OIDCConfig):
        self._config = config
        self._active_requests: dict[str, AuthRequest] = dict()
        self._lock = threading.Lock()

    def get_managed_role(self) -> str:
        return self._config.lp_role

    def consume_request(self, state: str) -> AuthRequest | None:
        if state in self._active_requests:
            req = self._active_requests[state]
            del self._active_requests[state]
            return req
        return None

    def create_request(self, mc_username: str, is_legit: bool, dc_id: int, dc_name: str):
        with self._lock:
            state = secrets.token_urlsafe(32)
            while state in self._active_requests:
                state = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32) 
            params = {
                    "state": state,
                    "nonce": nonce,
                    "client_id": self._config.client_id,
                    "scope": "email openid",
                    "code_challeneg_method": "none",
                    "response_type": "code",
                    "redirect_uri": self._config.callback_url
                    }

            url = f"{self._config.auth_url}?{urlencode(params)}"
            request = AuthRequest(
                    url = url,
                    state = state,
                    nonce = nonce,
                    creation_time = time.time_ns() // 1000_000,
                    is_legit = is_legit,
                    mc_username = mc_username,
                    dc_id = dc_id,
                    dc_name = dc_name
                    )
            self._register_request(request)
            return request

    def _register_request(self, request):
        self._active_requests[request.state] = request




