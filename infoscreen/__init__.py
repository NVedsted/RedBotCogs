from infoscreen.rules import InfoScreens


async def setup(bot):
    c = InfoScreens(bot)
    await c.init()
    bot.add_cog(c)
