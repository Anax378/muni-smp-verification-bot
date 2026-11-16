from dataclasses import dataclass
import sqlite3
from typing import Callable, TypeVar
import config as c
import api
from contextlib import closing

@dataclass
class User:
        id: int
        email: str | None
        account_limit: int
        is_banned: bool

@dataclass
class Registration:
    id: int
    user_id: int
    discord_id: int | None
    discord_name: str | None
    player_name: str
    player_uuid: str
    is_legit: bool
    creation_time: int


T = TypeVar("T")

class SQLiteManager:
    def __init__(self, config: c.SQLiteConfig):
        self._config = config

    def _with_connection(self, f: Callable[[sqlite3.Connection], T]) -> T:
        try:
            with closing(sqlite3.connect(self._config.filename)) as connection:
                with connection:
                    self._ensure_tables_exists(connection)
                    return f(connection)
        except sqlite3.OperationalError as e:
            print(e)
            raise api.BotException("There was an operational error while interacting with the database")
        except sqlite3.IntegrityError as e:
            print(e)
            raise api.BotException("A database constraint would be violated")


    def get_user_by_id(self, id: int) -> User:
        return self._with_connection(
                lambda connection: User(*connection.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (id,)
                    ).fetchone())
                )

    def get_email_bans(self) -> list[str]:
        return self._with_connection(
            lambda connection: [
                email
                for (email,) in connection.execute(
                    "SELECT email FROM users WHERE is_banned = TRUE"
                ).fetchall()
                if email is not None
            ]
        )


    def is_email_banned(self, email: str) -> bool:
        return self._with_connection(
            lambda connection: connection.execute(
                "SELECT 1 FROM users WHERE email = ? AND is_banned = TRUE",
                (email,)
            ).fetchone() is not None
        )


    def get_registrations_by_user_id(self, id: int) -> list[Registration]:
        return self._with_connection(
                lambda connection: [Registration(*row) for row in
                    connection.execute(
                        "SELECT * FROM registrations WHERE user_id = ?",
                        (id,)
                    ).fetchall()]
        )

    def get_registrations_by_dc_name(self, dc_name: str) -> list[Registration]:
        return self._with_connection(
                lambda connection: [Registration(*row) for row in
                                    connection.execute(
                                        "SELECT * FROM registrations WHERE discord_name = ?",
                                        (dc_name,))
                                    .fetchall()
                                    ]
                )

    def ban_email(self, email: str):
        def run(con):
            user = self._get_user_by_email(email, con)
            if user is None:
                con.execute("INSERT INTO users (email, is_banned) VALUES (?, TRUE)", (email,))
            else:
                con.execute("UPDATE users SET is_banned = TRUE WHERE id = ?", (user.id,))
        self._with_connection(run)
    
    def unban_email(self, email: str):
        self._with_connection(lambda con: con.execute("UPDATE users SET is_banned = FALSE where email = ?", (email,)))

    def get_acc_limit(self, email: str) -> int | None:
        lim = self._with_connection(lambda con: con.execute(
            "SELECT account_limit FROM users WHERE email = ?",
            (email,)
            ).fetchone())

        return None if lim is None else lim[0]

    def set_acc_limit(self, email, limit):
        def run(con):
            user = self._get_user_by_email(email, con)
            if user is None:
                con.execute(
                        "INERT INTO users (email, account_limit) VALUES (?, ?)",
                        (email, limit))
            else:
                con.execute(
                        "UPDATE users SET account_limit = ? WHERE email = ?",
                        (limit, email))
        self._with_connection(run)

    def validate_and_register(
            self,
            email: str,
            player_name: str,
            player_uuid: str,
            is_legit: bool,
            dc_id: int | None,
            dc_name: str | None,
            creation_time: str | None
            ):
        def run(connection: sqlite3.Connection):
            self._ensure_tables_exists(connection)
            self._validate_registration(email, player_name, player_uuid, connection, dc_id)
            user = self._get_user_by_email(email, connection)
            if user is None:
                connection.execute(
                        "INSERT INTO users (email) VALUES (?)",
                        (email,))

            user = self._get_user_by_email(email, connection)
            if user is None:
                raise api.BotException("Failed to create user in database")
            
            connection.execute(
                    """
                    INSERT INTO registrations (
                        user_id,
                        discord_id,
                        discord_name,
                        player_name,
                        player_uuid,
                        is_legit,
                        creation_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user.id, dc_id, dc_name, player_name, player_uuid, is_legit, creation_time)
                )
        self._with_connection(run)

    def get_user_by_email(self, email: str) -> User | None:
        return self._with_connection(
                lambda connection: self._get_user_by_email(email, connection)
        )

    def _get_user_by_email(
            self,
            email: str,
            connection: sqlite3.Connection
            ) -> User | None:
        result = connection.execute(
                "SELECT id, email, account_limit, is_banned FROM users WHERE email = ?",
                (email,)
                ).fetchone()

        return result and User(*result)

    def _validate_registration(
            self,
            email: str,
            player_name: str,
            player_uuid: str,
            connection: sqlite3.Connection,
            discord_id: int | None,
            ):

        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()

        player_name_exists = connection.execute(
                "SELECT 1 FROM registrations WHERE player_name = ?",
                (player_name,)).fetchone()

        if player_name_exists:
            raise api.BotException(f"registration(s) for the player {player_name} already exist")

        player_uuid_exists = connection.execute(
                "SELECT 1 FROM registrations WHERE player_uuid = ?",
                (player_uuid,)).fetchone()
        
        if player_uuid_exists:
            raise api.BotException(f"registration(s) for the player uuid {player_uuid} already exist")
        
        user = connection.execute(
                "SELECT id, account_limit, is_banned FROM users WHERE email = ?",
                (email,)
                ).fetchone()

        if user is None:
            return None

        user_id, account_limit, is_banned = user

        if is_banned:
            raise api.BotException(f"{email} is banned")
        
        count = connection.execute(
                "SELECT COUNT(*) FROM registrations WHERE user_id = ?",
                (user_id,)).fetchone()[0]
        
        if count >= account_limit:
            raise api.BotException(f"{email} canot register any more MC accounts")


    def _ensure_tables_exists(self, connection: sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS users (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           email TEXT UNIQUE,
                           account_limit INTEGER NOT NULL DEFAULT 1,
                           is_banned BOOLEAN NOT NULL DEFAULT FALSE
                                CHECK (is_banned IN (0, 1))
                           )
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS registrations (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           user_id INTEGER NOT NULL,
                           discord_id TEXT,
                           discord_name TEXT,
                           player_name TEXT NOT NULL UNIQUE,
                           player_uuid TEXT NOT NULL UNIQUE,
                           is_legit BOOLEAN NOT NULL
                                CHECK (is_legit IN (0, 1)),
                           creation_time INTEGER NOT NULL DEFAULT (
                               CAST(unixepoch('subsec') * 1000 AS INTEGER)
                               ),

                           FOREIGN KEY (user_id) REFERENCES users(id)

                           )  
                       """)




