import socket
import re
import time
import hashlib
import uuid
import aiohttp
from config import LPBConfig, dataclass
import api

async def retrieve_online_uuid(username) -> uuid.UUID | None:
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.mojang.com/users/profiles/minecraft/"+username) as response:
            json = await response.json()
            if "id" in json:
                return uuid.UUID(json["id"])
            else:
                return None


def calculate_offline_uuid(username) -> uuid.UUID:
    data = ("OfflinePlayer:"+username).encode("UTF-8")
    md5 = hashlib.md5(data).digest()
    return uuid.UUID(bytes=md5, version=3)


def validate_username(username):
    return re.fullmatch("[a-zA-Z0-9_]{3,16}", username) is not None



class LPBClient:
    def __init__(self, config: LPBConfig):
        self._config = config

    def set_role(self, role: str, uuid: str) -> str:
        return self.send_command(f"SET-ROLE {role} {uuid};")

    def add_role(self, role: str, uuid: str) -> str:
        return self.send_command(f"ADD-ROLE {role} {uuid};")
    
    def rem_role(self, role: str, uuid: str) -> str:
        return self.send_command(f"REM-ROLE {role} {uuid};")

    def has_role(self, role: str, uuid: str) -> str:
        return self.send_command(f"HAS-ROLE {role} {uuid};")

    def set_default_role(self, uuid: str) -> str:
        return self.send_command(f"SET-DEF-ROLE {uuid};")

    def move_player_name(self, player: str, server: str) -> str:
        return self.send_command(f"MOVE-PLAYER-NAME {server} {player};")

    def move_player_uuid(self, uuid: str, server: str) -> str:
        return self.send_command(f"MOVE-PLAYER-UUID {server} {uuid};")

    def send_command(self, command: str) -> str:
        timestamp = str(int(time.time() * 1000))
        
        digest = hashlib.sha256()
        digest.update(timestamp.encode('ascii'))
        digest.update(b' ')
        digest.update(command.encode('ascii'))
        digest.update(self._config.secret_salt.encode('ascii'))
        
        hex_digest = digest.hexdigest()
        payload = f"{hex_digest} {timestamp} {command}"
        return self.send_raw(payload)

    def send_raw(self, payload):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self._config.host, self._config.port))
            s.sendall(payload.encode('ascii'))
            response_chars = []
            while True:
                char = s.recv(1)
                if not char:
                    break
                
                decoded_char = char.decode('ascii', errors='ignore')
                response_chars.append(decoded_char)
                
                if decoded_char == ';':
                    break
                    
            return "".join(response_chars)


def has_role(role: str, uuid: str, client: LPBClient) -> bool:
    response = client.has_role(role, uuid)
    parts = response.rstrip(";").split(" ", maxsplit=1)
    if parts[0] != "OK" or len(parts) < 2:
        raise api.BotException(
                "MC Server vrátil neočekávanou odpověď na dotaz o stavu role: "+response)

    return parts[1] == "TRUE"

async def validate_verification(
        username: str,
        is_legit: bool,
        oidcmgr: api.OIDCManager,
        lpb_client: LPBClient
        ) -> uuid.UUID:
    if not validate_username(username):
        raise api.BotException(
                "neplatný Minecraft username (délka 3-16 znaků, znaky a-z, A-Z, 0-9 nebo _)")

    uuid = None
    offline_uuid = calculate_offline_uuid(username)
    online_uuid = None
    try:
        online_uuid = await retrieve_online_uuid(username)

        if is_legit and online_uuid is None:
            raise api.BotException("Nepodařilo se najít tvůj MC username přes Mojang api")

        uuid = online_uuid if is_legit else offline_uuid
        assert uuid is not None # uuid can never be None, but the lsp is too stupid to know that

    except OSError as e:
        raise api.BotException(
                "nepodařilo se kontaktovat mojang api pro uuid tvojeho mc username"+username)

    try:
        online_has_role = has_role(
                oidcmgr.get_managed_role(),
                str(online_uuid),
                lpb_client
        )

        offline_has_role = has_role(
                oidcmgr.get_managed_role(),
                str(offline_uuid),
                lpb_client
        )

        if online_has_role or offline_has_role: 
            raise api.BotException(username + " je už registrovaný")

    except OSError as e:
        raise api.BotException("Nepodařilo se kontaktovat MC server ohledně stavu role")

    return uuid


