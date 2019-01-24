from .purge import Purge


def setup(bot):
    bot.add_cog(Purge(bot))
