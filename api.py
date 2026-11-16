from warnings import catch_warnings
from aiohttp import BasicAuth, web
import aiohttp
from config import OIDCConfig
from oidc import OIDCManager
import api
import mc
import dcbot
import sqlite

class BotException(Exception):
    def __init__(self, message):
        self.message = message


class OIDCApi:
    def __init__(
            self,
            config: OIDCConfig,
            manager: OIDCManager,
            lpb_client: mc.LPBClient,
            bot: dcbot.DCBot,
            sqlite_mgr: sqlite.SQLiteManager 
            ):
        self._sqlite_mgr = sqlite_mgr
        self._lpb_client = lpb_client
        self._config: OIDCConfig = config
        self._manager: OIDCManager = manager
        self._dcbot = bot
        self.app = web.Application()
        self.app.add_routes([
            web.get("/api/verify", self.verify)
        ])

    async def verify(self, request: web.Request):
        try:
            state = request.query.get("state")
            code = request.query.get("code")
            if state is None or code is None:
                raise BotException("Missing state or code in the request json")

            oidc_request = self._manager.consume_request(state)
            if oidc_request is None:
                raise BotException("OIDC Request expired (or never existed)")

            uuid = await mc.validate_verification(
                    oidc_request.mc_username,
                    oidc_request.is_legit,
                    self._manager,
                    self._lpb_client
            )

            try:
                resp = (await self.request_token(code))
            except OSError as e:
                raise BotException("Could not retrieve the token")
            
            if "access_token" not in resp:
                raise BotException("The token is missing from the token service response")

            token = resp["access_token"]

            info = None
            try:
                info = await self.request_info(token)
            except OSError as e:
                raise BotException("Could not retrieve user info from the user info service")

            if "sub" not in info:
                raise BotException("The sub field is missing from the user info service")
            
            email = info["sub"]
            self._sqlite_mgr.validate_and_register(
                    email,
                    oidc_request.mc_username,
                    str(uuid),
                    oidc_request.is_legit,
                    oidc_request.dc_id,
                    oidc_request.dc_name,
                    str(oidc_request.creation_time)
                    )
            
            self._lpb_client.add_role(self._config.lp_role, str(uuid))
            self._dcbot.run_finalize_verification(oidc_request.dc_id, oidc_request.mc_username)

        except BotException as e:
            return web.json_response({
                "success": False,
                "message": e.message
                })
        return web.json_response({
            "success": True,
            "message": "sucessfully verified " + oidc_request.mc_username 
            })


    async def request_token(self, code: str):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://id.muni.cz/oidc/token",
                    auth = BasicAuth(
                        self._config.client_id,
                        self._config.client_secret
                        ),
                    params = {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self._config.callback_url
                        }
                    ) as response :
                return await response.json()


    async def request_info(self, token):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    self._config.userinfo_url,
                    headers={"Authorization": "Bearer "+token}
                    ) as response:
                return await response.json()


