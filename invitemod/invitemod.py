import discord
from discord import Message, NotFound
from discord.invite import Invite
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting, common_filters


def get_invites(msg):
    """Finds all invites in a message."""
    return common_filters.INVITE_URL_RE.findall(msg)


class InviteMod(commands.Cog):
    """Moderates invite links"""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot

        self.config = Config.get_conf(self, identifier=87484165135)
        default_guild = {
            'whitelist': [],
            'logging_channel': 0,
        }
        self.config.register_guild(**default_guild)

    @commands.command()
    @checks.admin()
    async def invite_whitelist(self, ctx: commands.context.Context):
        """Shows which guilds are whitelisted."""
        whitelist = await self.config.guild(ctx.guild).whitelist()
        if len(whitelist) > 0:
            formatted_whitelist = '\n'.join(
                "%d. %s" % (index + 1, guild_id) for index, guild_id in enumerate(whitelist))
        else:
            formatted_whitelist = 'None'
        await ctx.send("The following guild IDs are whitelisted:" + chat_formatting.box(formatted_whitelist))

    @commands.command()
    @checks.admin()
    async def invite_whitelist_add(self, ctx: commands.context.Context, guild_id: int):
        """Adds a guild ID to the invite whitelist."""
        whitelist = await self.config.guild(ctx.guild).whitelist()
        if guild_id not in whitelist:
            whitelist.append(guild_id)
            await self.config.guild(ctx.guild).whitelist.set(whitelist)
            await ctx.send("Added %s to the whitelist." % guild_id)
        else:
            await ctx.send("%s is already whitelisted." % guild_id)

    @commands.command()
    @checks.admin()
    async def invite_whitelist_remove(self, ctx: commands.context.Context, guild_id: int):
        """Removes a guild ID from the invite whitelist."""
        whitelist = await self.config.guild(ctx.guild).whitelist()
        if guild_id in whitelist:
            whitelist.remove(guild_id)
            await self.config.guild(ctx.guild).whitelist.set(whitelist)
            await ctx.send("Removed %s from the whitelist." % guild_id)
        else:
            await ctx.send("%s is not on the whitelist." % guild_id)

    @commands.command()
    @checks.admin()
    async def invite_whitelist_logging(self, ctx: commands.context.Context, channel: discord.TextChannel = None):
        """Sets the logging channel for invite infractions."""
        if channel:
            await self.config.guild(ctx.guild).logging_channel.set(channel.id)
            await ctx.send("Set logging channel to %s." % channel.mention)
        else:
            await self.config.guild(ctx.guild).logging_channel.set(0)
            await ctx.send("Cleared logging channel.")

    async def handle_invite(self, message: discord.Message, code):
        """Handles an invite code on a given message."""
        try:
            invite: Invite = await self.bot.fetch_invite(code)
        except NotFound:
            return False

        if not invite.guild:
            return False

        whitelist = await self.config.guild(message.guild).whitelist()
        if invite.guild.id not in whitelist:
            await message.delete()
            log = "[%s] :space_invader: %s (%s) posted an invite link to a server (%s, %s) that is not whitelisted " \
                  "and their message was removed." % (
                      chat_formatting.inline(message.created_at.strftime("%H:%M:%S")),
                      message.author,
                      chat_formatting.inline(str(message.author.id)),
                      invite.guild.name,
                      chat_formatting.inline(str(invite))
                  )
            await self.log(message.guild, log)
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        """Processes invites in incoming messages."""
        if message.author.bot:
            return
        for _, code in get_invites(message.content):
            did_delete = await self.handle_invite(message, code)
            if did_delete:
                break

    async def log(self, guild: discord.Guild, log: str):
        """Logs to the logging channel if possible."""
        channel_id = await self.config.guild(guild).logging_channel()
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        await channel.send(log)
