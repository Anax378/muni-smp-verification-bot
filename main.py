import api
import threading
import mc
import dcbot
import config as c
from aiohttp import web
import sqlite

if __name__ == "__main__":
    cs = c.readConfigs()

    manager = api.OIDCManager(cs.oidc_config)
    client = mc.LPBClient(cs.lpb_config)
    sqlite_manager = sqlite.SQLiteManager(cs.sqlite_config)
    bot = dcbot.DCBot(cs.dcbot_config, client, manager, sqlite_manager)
    oidc_api = api.OIDCApi(cs.oidc_config, manager, client, bot, sqlite_manager)

    threading.Thread(target=bot.run).start()
    web.run_app(oidc_api.app, host="127.0.0.1", port=8081)


