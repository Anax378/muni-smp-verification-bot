import asyncio
from datetime import datetime
from config import DCBotConfig
from discord.ext import commands
from discord import app_commands
import api
import discord
import mc
import oidc
import sqlite

ACCOUNT_TYPE_LEGIT = "legit"
ACCOUNT_TYPE_WAREZ = "warez"

def format_time(epoch_millis: int) -> str:
    return datetime.fromtimestamp(epoch_millis / 1000).strftime("%d.%m.%Y %H:%M:%S")

class RegistrationModal(discord.ui.Modal):
    def __init__(self, config: DCBotConfig, lpb_client: mc.LPBClient, oidcmgr: oidc.OIDCManager):
        self._oidcmgr = oidcmgr
        self._config = config
        self._lpb_client = lpb_client
        super().__init__(title="Verify with MUNI")
        self.mcname = discord.ui.TextInput(
                placeholder="username",
                max_length=32
                )

        self.account_type = discord.ui.Select(
                placeholder="Zvol typ MC účtu",
                min_values=1,
                max_values=1,
                required=True,
                options = [
                    discord.SelectOption(
                        label="Budu hrát s koupeným Minecraft účtem",
                        value=ACCOUNT_TYPE_LEGIT,
                        default=True
                        ),
                    discord.SelectOption(
                        label="Yarr! (warez)",
                        value=ACCOUNT_TYPE_WAREZ
                        )
                    ]
                )

        self.add_item(discord.ui.Label(
            text="Minecraft username",
            component=self.mcname
            ))
        self.add_item(discord.ui.Label(
            text="Typ účtu",
            component=self.account_type
            ))

    async def on_submit(self, interaction: discord.Interaction):
        async def respond(msg: str):
            await interaction.followup.send(msg, ephemeral=True)

        try:
            await interaction.response.defer()
            await respond("zpracovávám...")

            username = self.mcname.value
            account_type = self.account_type.values[0]
            is_legit = account_type == ACCOUNT_TYPE_LEGIT

            dc_id = interaction.user.id
            guild = interaction.guild
            if guild is None:
                raise api.BotException("The guild is None. (are you using the bot in a discord server ?)")

            await mc.validate_verification(
                    username,
                    is_legit,
                    self._oidcmgr,
                    self._lpb_client,
            )
            await respond(f"Přihlaš se prosím přes MUNI: " + self._oidcmgr.create_request(
                username,
                is_legit,
                interaction.user.id,
                interaction.user.name
                ).url)
        except api.BotException as e:
            await respond(e.message)

class DCBot():
    def __init__(
            self,
            config: DCBotConfig,
            lpb_client: mc.LPBClient,
            oidcmgr: oidc.OIDCManager,
            sqlite_mgr: sqlite.SQLiteManager
            ):
        self._sqlite_mgr = sqlite_mgr
        self._oidcmgr = oidcmgr
        self._lpb_client = lpb_client
        self._config = config
        intents = discord.Intents.default()
        intents.members = True
        self._bot = commands.Bot(command_prefix='!', intents=intents)

        self._bot.tree.command(
                name="verify",
                description="Verify with MUNI via OIDC"
        )(self.register)

        self._bot.tree.command(
                name="regs_by_dc_name",
                description="Get all registrations created by the user with this name"
        )(self.regs_by_dc_name)
        
        self._bot.tree.command(
                name="regs_by_email",
                description="Get all registrations using this email"
        )(self.regs_by_email)

        self._bot.tree.command(
            name="get_email_bans",
            description="List all banned email addresses"
        )(self.get_email_bans)

        self._bot.tree.command(
            name="is_email_banned",
            description="Check whether an email is banned"
        )(self.is_email_banned)

        self._bot.tree.command(
            name="ban_email",
            description="Ban an email address"
        )(self.ban_email)

        self._bot.tree.command(
            name="unban_email",
            description="Unban an email address"
        )(self.unban_email)

        self._bot.tree.command(
                name="get_email_acc_limit",
                description="Get how many MC accounts this email can register"
        )(self.get_email_acc_limit)

        self._bot.tree.command(
                name="set_email_acc_limit",
                description="Set how many MC accounts this email can register"
        )(self.set_email_acc_limit)

        async def setup_hook():
            commands = await self._bot.tree.sync()
            print(f"synced {len(commands)} commands")

        self._bot.setup_hook = setup_hook

    def run(self):
        self._bot.run(self._config.token)

    def _validate_has_role(self, interaction, role):
        user = interaction.user
        if not isinstance(user, discord.Member):
            raise api.BotException("Toto lze dělat pouze v discord serveru")
        if role not in [role.id for role in user.roles]:
            raise api.BotException("Na toto nemáš oprávnění")

    async def set_email_acc_limit(self, interaction, email: str, limit: int):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            self._sqlite_mgr.set_acc_limit(email, limit)
            await interaction.response.send_message(f"set limit to {limit} for {email}", ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)

    async def get_email_acc_limit(self, interaction, email: str):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            limit = self._sqlite_mgr.get_acc_limit(email)
            if limit is None:
                await interaction.response.send_message(f"no one uses the email {email}", ephemeral=True)
            else:
                await interaction.response.send_message(f"the limit for {email} is {limit}", ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)

    async def unban_email(self, interaction, email: str):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            self._sqlite_mgr.unban_email(email)
            await interaction.response.send_message(f"unbanned {email}", ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)
    
    async def ban_email(self, interaction, email: str):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            user = self._sqlite_mgr.get_user_by_email(email)
            regs = []
            if user is not None:
                regs = self._sqlite_mgr.get_registrations_by_user_id(user.id)
            self._sqlite_mgr.ban_email(email)

            for reg in regs:
                self._lpb_client.rem_role(self._oidcmgr.get_managed_role(), reg.player_uuid)
                self._lpb_client.move_player_uuid(reg.player_uuid, self._config.mc_lobby_server_name)
            await interaction.response.send_message(f"banned {email}", ephemeral=True)

        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)
            

    async def get_email_bans(self, interaction):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            bans = self._sqlite_mgr.get_email_bans()
            if not bans:
                await interaction.response.send_message("There are no email bans", ephemeral=True)
            else:
                await interaction.response.send_message("email bans: \n" + "\n".join(bans), ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)

    async def is_email_banned(self, interaction, email: str):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            await interaction.response.send_message(
                    f"{email}" + ("is banned" if self._sqlite_mgr.is_email_banned(email) else "is not banned"),
                    ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)


    async def regs_by_email(self, interaction: discord.Interaction, email: str):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            user = self._sqlite_mgr.get_user_by_email(email)
            if user is None:
                await interaction.response.send_message(f"No one uses the email {email}", ephemeral=True)
                return
            regs = self._sqlite_mgr.get_registrations_by_user_id(user.id)
            if not regs:
                await interaction.response.send_message(f"{email} nemá žádné registrace", ephemeral=True)

            await interaction.response.send_message(self.format_regs(regs), ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)

    def format_regs(self, regs: list[sqlite.Registration]):
        return "<time> \" - \" (\" (warez)\" | \"\") <player-name> <player-uuid> \"na email\" <email> \"z discord profilu\" <discord-name> \"(\"<discord-id>\")\"\n" + "\n".join(
                [f"{format_time(reg.creation_time)} - {'' if reg.is_legit else '(warez) '} {reg.player_name} {reg.player_uuid} na email {self._sqlite_mgr.get_user_by_id(reg.user_id).email} z discord profilu  {reg.discord_name} ({reg.discord_id})"
                     for reg in regs]
        )

    async def regs_by_dc_name(self, interaction: discord.Interaction, user: str):
        try:
            self._validate_has_role(interaction, self._config.admin_role_id)
            regs = self._sqlite_mgr.get_registrations_by_dc_name(user)
            if not regs:
                await interaction.response.send_message(f"{user} nemá žádné registrace", ephemeral=True)

            await interaction.response.send_message(self.format_regs(regs), ephemeral=True)
        except api.BotException as e:
            await interaction.response.send_message(e.message, ephemeral=True)
    

    async def register(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RegistrationModal(
            self._config,
            self._lpb_client,
            self._oidcmgr
            ))

    async def _finalize_verification(self, dc_id: int, mc_username: str):
        guild = self._bot.get_guild( self._config.guild_id)\
                or await self._bot.fetch_guild(self._config.guild_id)

        if guild is None:
            raise api.BotException(
                    "Discord finalization failed: Could not retrieve guild. (it is None). MC rights were granted")

        member = await guild.fetch_member(dc_id)
        name = member.display_name
        newnick = f"[{name}]" if name == mc_username else name+f" [{mc_username}]"

        role = guild.get_role(self._config.mc_rights_role_id) or await guild.fetch_role(self._config.mc_rights_role_id)
        try:
            await member.add_roles(role, reason="OIDC verification")
        except discord.Forbidden:
            raise api.BotException(
                    f"Could not give {name} discord role: Permission denied. MC rights were granted to {mc_username}.")
        try: 
            await member.edit(
                    nick = newnick,
                    reason = "OIDC verification"
                    )
        except discord.Forbidden:
            raise api.BotException(
                    f"Could not change nick of user {name}: Permission denied. MC rights were granted to {mc_username}.")

    def run_finalize_verification(self, dc_id: int, mc_username: str):
        future = asyncio.run_coroutine_threadsafe(
                self._finalize_verification(dc_id, mc_username),
                self._bot.loop
                )

        return future.result()

        




