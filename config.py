from dataclasses import dataclass
import configparser
import os

@dataclass
class OIDCConfig:
    client_id: str
    client_secret: str
    auth_url: str
    callback_url: str
    userinfo_url: str
    lp_role: str

@dataclass
class LPBConfig:
    secret_salt: str
    host: str
    port: int

@dataclass
class DCBotConfig:
    token: str
    guild_id: int
    mc_rights_role_id: int
    admin_role_id: int
    mc_lobby_server_name: str

@dataclass
class SQLiteConfig:
    filename: str = "database.db"

@dataclass
class AllConfigs:
    oidc_config: OIDCConfig
    lpb_config: LPBConfig
    dcbot_config: DCBotConfig
    sqlite_config: SQLiteConfig

def readConfigs(cfg_path: str = "config.ini"): 
    config = configparser.ConfigParser()

    config["oidc"] = {
            "client_id": "CHANGEME",
            "client_secret": "CHANGEME",
            "auth_url": "CHANGEME",
            "callback_url": "CHANGEME",
            "userinfo_url": "CHANGEME",
            "lp_role": "CHANGEME"
            }
    config["lpb"] = {
            "secret_salt": "CHANGEME",
            "host": "localhost",
            "port": "25567"
            }
    config["dcbot"] = {
            "token": "CHANGEME",
            "guild_id": "CHANGEME",
            "mc_rights_role_id": "CHANGEME",
            "admin_role_id": "CHANGEME",
            "mc_lobby_server_name": "lobby"
            }
    config["sqlite"] = {"filename": "database.db"}

    if not os.path.exists(cfg_path):
        with open(cfg_path, "w") as f:
            config.write(f)

    config.read(cfg_path)


    oidc_config = OIDCConfig(**dict(config["oidc"]))
    lpb_config = LPBConfig(**dict(config["lpb"]))
    dcbot_config = DCBotConfig(**dict(config["dcbot"]))
    sqlite_config = SQLiteConfig(**dict(config["sqlite"]))

    lpb_config.port = int(config["lpb"]["port"])
    dcbot_config.guild_id = int(config["dcbot"]["guild_id"])
    dcbot_config.mc_rights_role_id = int(config["dcbot"]["mc_rights_role_id"])
    dcbot_config.admin_role_id = int(config["dcbot"]["admin_role_id"])

    return AllConfigs(oidc_config, lpb_config, dcbot_config, sqlite_config)


