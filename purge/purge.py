import asyncio
from datetime import datetime, timedelta, time
from redbot.core import commands, Config, checks

#: The timestamp to begin the daily purge. (E.g. 23:30:00 -> time(23, 30, 0))
purge_time = time(23, 30, 0)

#: The amount of minutes to wait after warning that a purge is coming up and actually purging.
wait_period = 5


async def clean_channel(channel):
    await channel.purge(after=datetime.now() - timedelta(days=14))


async def _daily_purge(channel):
    await channel.send("This channel will be purged in {} minutes.".format(wait_period))
    await asyncio.sleep(wait_period * 60)
    await clean_channel(channel)


def response_check(message):
    return lambda m: m.author == message.author and m.channel == message.channel


class Purge(commands.Cog):
    """This cog can periodically clean up channels."""

    def __init__(self, bot):
        super().__init__()
        self.config = Config.get_conf(self, identifier=1170348762)
        self.config.register_guild(channels=[])
        self.bot = bot
        self.bot.loop.create_task(self.daily_loop())

    @commands.command(no_pm=True)
    @checks.admin()
    async def purge(self, ctx):
        """Purges the current channel now."""
        await ctx.send(
            'Are you sure you want to purge {} right now? Type `yes` to confirm.'.format(ctx.channel.mention))

        response = await self.bot.wait_for('message', check=response_check(ctx.message))

        if response.content.lower().strip() == "yes":
            await clean_channel(ctx.channel)
        else:
            await ctx.send("Aborting purge.")

    @commands.command(no_pm=True)
    @checks.admin()
    async def purgedailynow(self, ctx):
        """Starts the daily purge routine now for this server."""
        await ctx.send(
            'Commence daily purge for this server? Type `yes` to confirm.'.format(ctx.channel.mention)
        )

        response = await ctx.bot.wait_for('message', check=response_check(ctx.message))

        if response.content.lower().strip() == "yes":
            channels = await self.config.guild(ctx.guild).channels()
            await self.daily_purge_channels(channels)
        else:
            await ctx.send("Aborting daily purge.")

    @commands.command(no_pm=True)
    @checks.admin()
    async def purgeadd(self, ctx):
        """Adds this channel to the daily purge."""
        guild_config = self.config.guild(ctx.guild)
        channels = await guild_config.channels()
        if ctx.channel.id not in channels:
            channels.append(ctx.channel.id)
            await guild_config.channels.set(channels)
            await ctx.send('I will now purge {} daily.'.format(ctx.channel.mention))
        else:
            await ctx.send('I am already purging {} daily.'.format(ctx.channel.mention))

    @commands.command(no_pm=True)
    @checks.admin()
    async def purgeremove(self, ctx):
        """Removes this channel from the daily purge."""
        channels = await self.config.guild(ctx.guild).channels()
        if ctx.channel.id not in channels:
            await ctx.send('I am not purging {} daily.'.format(ctx.channel.mention))
        else:
            channels.remove(ctx.channel.id)
            await self.config.guild(ctx.guild).channels.set(channels)
            await ctx.send('I am no longer purging {} daily.'.format(ctx.channel.mention))

    @commands.command(no_pm=True)
    @checks.admin()
    async def purging(self, ctx):
        """Checks if this channel is being purged daily."""
        channels = await self.config.guild(ctx.guild).channels()
        if ctx.guild.id in channels:
            await ctx.send("I purge {} daily.".format(ctx.channel.mention))
        else:
            await ctx.send("I don't purge {} daily.".format(ctx.channel.mention))

    @commands.command(no_pm=True)
    @checks.admin()
    async def purgelist(self, ctx):
        """Lists all channels that are being purged daily on this server."""
        await self._clean_channels_list(ctx.guild)
        channels = await self.config.guild(ctx.guild).channels()
        if len(channels) == 0:
            await ctx.send("I don't purge any channels in this server.")
        else:
            channels_mentions = "\n".join([ctx.guild.get_channel(c).mention for c in channels])
            await ctx.send('I purge the following channels:\n{}'.format(channels_mentions))

    async def _clean_channels_list(self, guild):
        guild_config = self.config.guild(guild)
        channels = await guild_config.channels()
        await guild_config.channels.set([c for c in channels if self.bot.get_channel(c) is not None])

    async def daily_purge_channels(self, channels):
        tasks = []
        for channel_id in channels:
            tasks.append(_daily_purge(self.bot.get_channel(channel_id)))
        await asyncio.gather(*tasks)

    async def daily_loop(self):
        while True:
            date = datetime.now().date()
            next_execution = datetime.combine(date, purge_time)
            if next_execution < datetime.now():
                next_execution += timedelta(days=1)
            seconds_remaining = (next_execution - datetime.now()).seconds
            print("Preparing to execute daily purge in {} seconds.".format(seconds_remaining))
            await asyncio.sleep(seconds_remaining)
            print("Start daily purge.")
            tasks = []
            guilds_data = await self.config.all_guilds()
            for guild_id, data in guilds_data.items():
                await self.daily_purge_channels(data["channels"])
            await asyncio.gather(*tasks)
