import io

import discord
import requests

from redbot.core import commands, Config, checks

INFO_TEXT = 'text'
INFO_IMAGE = 'image'
INFO_TEXT_BOX = 'textbox'
INFO_LIST = 'list'


def editor_check(editor, channel):
    return lambda m: m.channel == channel and m.author == editor


def get_or_empty(d, k):
    return d.get(k, discord.Embed.Empty)


def get_basic_embed(o):
    return discord.Embed(
        title=get_or_empty(o, 'title'),
        description=get_or_empty(o, 'description'),
        color=get_or_empty(o, 'color')
    )


def describe(element):
    t = element['entry_type']
    o = element['options']
    if t == INFO_TEXT:
        return 'A text field containing "%s".' % truncate(o['text'], 25)
    elif t == INFO_LIST:
        message = 'A'
        if 'enumerated' in o and o['enumerated']:
            message += ' numbered'
        message += ' list'
        if 'title' in o:
            message += ' titled %s' % o['title']
        message += ' containing %d entries.' % len(o['entries'])
        return message
    elif t == INFO_IMAGE:
        message = 'An'
        if 'raw' not in o or not o['raw']:
            message += ' embedded'
        return message + ' image from URL %s.' % o['url']
    elif t == INFO_TEXT_BOX:
        message = 'A text box.'
        if 'title' in o:
            message += ' Title is "%s".' % truncate(o['title'], 25)
        if 'description' in o:
            message += ' Description is "%s".' % truncate(o['description'], 25)
        return message


async def get_answer(bot, channel, editor, *, allow_delete=True, strip=False, lower=False):
    msg = await bot.wait_for('message', check=editor_check(editor, channel))
    if allow_delete and msg.content.strip() == '!':
        return None
    else:
        content = msg.content
        if strip:
            content = content.strip()
        if lower:
            content = content.lower()
        return content


async def edit_color_option(bot, channel, editor, options):
    await channel.send('Enter a new color HEX (type ! to delete):')
    value = await get_answer(bot, channel, editor, strip=True, lower=True)
    if value is None:
        if 'color' in options:
            del options['color']
        await channel.send('Color has been deleted.')
    else:
        try:
            color = int(value.replace('#', ''), 16)
            options['color'] = color
            await channel.send('Color is now set to: "%s"' % value)
        except ValueError:
            await channel.send('This is not a valid color. Aborting.')


async def edit_simple_option(bot, channel, editor, options, option, *, allow_delete=False):
    await channel.send('Enter a new %s%s:' % (option, ' (type ! to delete)' if allow_delete else ''))
    value = await get_answer(bot, channel, editor, allow_delete=True)
    if value is None:
        if option in options:
            del options[option]
        await channel.send('%s has been deleted.' % option.title())
    else:
        options[option] = value
        await channel.send('%s is now set to: "%s"' % (option.title(), value))


async def edit_list_entries(bot, channel, editor, entries):
    async def validate_index(i):
        try:
            i = int(i)
        except ValueError:
            await channel.send('That\'s not a valid number.')
            return None
        if 1 <= i <= len(entries):
            return i - 1
        else:
            await channel.send('The index should be between 1 and %d inclusive.' % len(entries))
            return None

    await channel.send('You\'re editing a list containing %d entries.\n' % len(entries) +
                       'Add with `a [#]`.\n' +
                       'Edit with `e [#]`.\n' +
                       'Delete with `d #`.\n' +
                       'Move with `m # #`.\n' +
                       'Swap with `s # #`.\n' +
                       'Get overview with `l`.\n'
                       'Quit with `q`.')
    while True:
        cmd = await get_answer(bot, channel, editor, strip=True, lower=True)
        args = cmd.split(' ')
        choice = args[0]
        if choice == 'q':
            break
        elif choice == 'l':
            if not entries:
                await channel.send('The list is empty.')
            else:
                await channel.send("\n".join(
                    ['%d. %s' % (index + 1, entry['name']) for index, entry in enumerate(entries)]
                ))
        elif choice == 'a':
            index = len(entries)
            if len(args) > 1:
                index = await validate_index(args[1])
                if index is None:
                    continue
            await channel.send('Title:')
            name = await get_answer(bot, channel, editor)
            await channel.send('Description:')
            value = await get_answer(bot, channel, editor)
            entries.insert(index, {'name': name, 'value': value})
            await channel.send('The list entry has been added.')
        elif choice == 'e':
            if len(args) != 2:
                await channel.send('You must provide an index: `e #`. Try again.')
                continue
            index = await validate_index(args[1])
            if index is None:
                continue
            await channel.send('Title:')
            name = await get_answer(bot, channel, editor)
            await channel.send('Description:')
            value = await get_answer(bot, channel, editor)
            entries[index] = {'name': name, 'value': value}
            await channel.send('The list entry has been edited.')
        elif choice == 'd':
            if len(args) != 2:
                await channel.send('You must provide an index: `d #`. Try again.')
                continue
            index = await validate_index(args[1])
            if index is None:
                continue
            del entries[index]
            await channel.send('The entry at index %d has been deleted.' % (index + 1))
        elif choice == 'm':
            if len(args) != 3:
                await channel.send('You must provide two indexes: `m # #`. Try again.')
                continue
            first_index = await validate_index(args[1])
            second_index = await validate_index(args[2])
            if first_index is None or second_index is None:
                continue
            entry = entries[first_index]
            del entries[first_index]
            entries.insert(second_index, entry)
            await channel.send(
                'The entry at index %d was moved to index %d' % (first_index + 1, second_index + 1)
            )
        elif choice == 's':
            if len(args) != 3:
                await channel.send('You must provide two indexes: `s # #`. Try again.')
                continue
            first_index = await validate_index(args[1])
            second_index = await validate_index(args[2])
            if first_index is None or second_index is None:
                continue
            tmp = entries[first_index]
            entries[first_index] = entries[second_index]
            entries[second_index] = tmp
            await channel.send(
                'The entry at index %d has been swapped with the entry at index %d' % (
                    first_index + 1, second_index + 1)
            )
        else:
            await channel.send('Invalid option. Try again.')


class BaseScreen:
    def __init__(self, elements=list()):
        self.elements = elements

    def add(self, entry_type, index=None, **options):
        if index is None:
            self.elements.append({'entry_type': entry_type, 'options': options})
        else:
            self.elements.insert(index, {'entry_type': entry_type, 'options': options})

    def remove(self, index):
        self.elements.pop(index)

    def is_empty(self):
        return len(self.elements) == 0

    def describe_all(self):
        return [describe(element) for element in self.elements]

    async def send(self, bot, destination):
        for element in self.elements:
            t = element['entry_type']
            o = element['options']
            if t == INFO_IMAGE:
                if 'raw' not in o or not o['raw']:
                    embed = discord.Embed(color=get_or_empty(o, 'color')).set_image(url=o['url'])
                    await destination.send(None, embed=embed)
                else:
                    r = requests.get(o['url'])
                    await destination.send(None, file=discord.File(io.BytesIO(r.content), "eh.jpg"))
            elif t == INFO_TEXT:
                await destination.send(o['text'])
            elif t == INFO_TEXT_BOX:
                embed = get_basic_embed(o)
                await destination.send(None, embed=embed)
            elif t == INFO_LIST:
                embed = get_basic_embed(o)
                for index, entry in enumerate(o['entries']):
                    name = entry['name']
                    if 'enumerated' in o and o['enumerated']:
                        name = str(index + 1) + '. ' + name
                    embed.add_field(inline=False, name=name, value=entry['value'])
                await destination.send(None, embed=embed)

    async def edit_entry(self, bot, channel, editor, index):
        entry = self.elements[index]
        t = entry['entry_type']
        o = entry['options']

        if t == INFO_TEXT:
            await edit_simple_option(bot, channel, editor, o, 'text')
        else:
            running = True
            while running:
                if t == INFO_TEXT_BOX:
                    await channel.send('Do you want to edit the [c]olor, [t]itle, or [d]escription?')
                    msg = await bot.wait_for('message', check=editor_check(editor, channel))
                    choice = msg.content.strip().lower()
                    if choice in ['c', 'color']:
                        await edit_color_option(bot, channel, editor, o)
                    elif choice in ['t', 'title']:
                        await edit_simple_option(bot, channel, editor, o, 'title', allow_delete=True)
                    elif choice in ['d', 'desc', 'description']:
                        await edit_simple_option(bot, channel, editor, o, 'description', allow_delete=True)
                    else:
                        await channel.send('That\'s not a valid option.')
                        continue
                if t == INFO_IMAGE:
                    await channel.send('Do you want to edit the [c]olor, [u]rl, or [r]aw?')
                    msg = await bot.wait_for('message', check=editor_check(editor, channel))
                    choice = msg.content.strip().lower()
                    if choice in ['c', 'color']:
                        await edit_color_option(bot, channel, editor, o)
                    elif choice in ['u', 'url']:
                        await edit_simple_option(bot, channel, editor, o, 'url')
                    elif choice in ['r', 'raw']:
                        if 'raw' not in o or not o['raw']:
                            o['raw'] = True
                            await channel.send('The image will now be sent raw.')
                        else:
                            o['raw'] = False
                            await channel.send('The image will now be sent in an embed.')
                    else:
                        await channel.send('That\'s not a valid option.')
                        continue
                elif t == INFO_LIST:
                    await channel.send(
                        'Do you want to edit the [c]olor, [t]itle, [d]escription, t[o]ggle numbers, or [e]ntries?'
                    )
                    choice = await get_answer(bot, channel, editor, strip=True, lower=True)
                    if choice in ['c', 'color']:
                        await edit_color_option(bot, channel, editor, o)
                    elif choice in ['t', 'title']:
                        await edit_simple_option(bot, channel, editor, o, 'title', allow_delete=True)
                    elif choice in ['d', 'desc', 'description']:
                        await edit_simple_option(bot, channel, editor, o, 'description', allow_delete=True)
                    elif choice in ['o', 'toggle', 'toggle numbers']:
                        if 'enumerated' in o and o['enumerated']:
                            del o['enumerated']
                            await channel.send('Numbering is now disabled.')
                        else:
                            o['enumerated'] = True
                            await channel.send('Numbering is now enabled.')
                    elif choice in ['e', 'entries', 'entry']:
                        await edit_list_entries(bot, channel, editor, o['entries'])
                    else:
                        await channel.send('That\'s not a valid option.')
                        continue
                await channel.send('Do you want to edit more? ([y]es/[n]o)')
                if await get_answer(bot, channel, editor, strip=True, lower=True) not in ['y', 'yes']:
                    running = False


def truncate(s, l):
    return (s[:75] + '...') if len(s) > l else s


class InfoScreen(commands.Cog):
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.file_path = 'data/infoscreen/screens.json'
        self.config = Config.get_conf(self, identifier=1170348762)
        self.config.register_global(screens={})
        self.screens = {}

    async def init(self):
        raw_screens = await self.config.screens()
        self.screens = {server_id: BaseScreen(elements) for server_id, elements in raw_screens.items()}

    def get_screen(self, server_id, *, create=False):
        screen = self.screens.get(server_id)
        if screen is None and create:
            screen = BaseScreen()
            self.screens[server_id] = screen
        return screen

    async def _validate_index(self, ctx, screen, index):
        if screen is None or len(screen.elements) == 0:
            await ctx.send('The info screen is empty.')
            return None
        try:
            index = int(index)
        except ValueError:
            await ctx.send('The index should be a number.')
            return None
        if 1 <= index <= len(screen.elements):
            return index - 1
        else:
            await ctx.send('The index should be between 1 and %d inclusive.' % len(screen.elements))
            return None

    async def save_screens(self):
        await self.config.screens.set({server_id: screen.elements for server_id, screen in self.screens.items()})

    @commands.command(no_pm=True)
    @checks.admin()
    async def infosend(self, ctx):
        """Sends the info screen in the current channel."""
        screen = self.get_screen(ctx.guild.id)
        if screen is None or screen.is_empty():
            await ctx.send('The info screen is empty.')
        else:
            await screen.send(self.bot, ctx.message.channel)

    @commands.command(no_pm=True)
    @checks.admin()
    async def infolist(self, ctx):
        """Lists entries in the info screen."""
        screen = self.get_screen(ctx.guild.id)
        if screen is None or screen.is_empty():
            await ctx.send('The info screen is empty.')
        else:
            message = 'Entries in info screen:\n'
            message += '\n'.join(
                ['%d. %s' % (index + 1, description) for index, description in enumerate(screen.describe_all())]
            )
            await ctx.send(message)

    @commands.command(no_pm=True)
    @checks.admin()
    async def infoadd(self, ctx, index=None):
        """Adds an entry."""
        screen = self.get_screen(ctx.guild.id, create=True)
        if index is not None:
            index = await self._validate_index(ctx, screen, index)
            if index is None:
                return

        await ctx.send('What type of entry? ([T]ext, text[b]ox, [l]ist, or [i]mage)')
        choice = await get_answer(self.bot, ctx.channel, ctx.author, strip=True, lower=True)
        if choice in ['t', 'text']:
            await ctx.send('Text:')
            text = await get_answer(self.bot, ctx.channel, ctx.author)
            screen.add(INFO_TEXT, index, text=text)
            await ctx.send('The text entry has been created.')
        elif choice in ['b', 'textbox']:
            screen.add(INFO_TEXT_BOX, index)
            await ctx.send('The text box entry has been created.')
            await screen.edit_entry(self.bot, ctx.channel, ctx.author, -1 if index is None else index)
        elif choice in ['l', 'list']:
            screen.add(INFO_LIST, index, entries=[])
            await ctx.send('The list entry has been created.')
            await screen.edit_entry(self.bot, ctx.channel, ctx.author, -1 if index is None else index)
        elif choice in ['i', 'image']:
            await ctx.send('URL:')
            url = await get_answer(self.bot, ctx.channel, ctx.author)
            screen.add(INFO_IMAGE, index, url=url)
            await ctx.send('The image entry has been created.')
        else:
            await ctx.send('Invalid type. Aborting.')
        await self.save_screens()

    @commands.command(no_pm=True)
    @checks.admin()
    async def infoedit(self, ctx, index):
        """Edits an entry."""
        screen = self.get_screen(ctx.guild.id)
        index = await self._validate_index(ctx, screen, index)
        if index is not None:
            await screen.edit_entry(self.bot, ctx.channel, ctx.author, index)
            await self.save_screens()

    @commands.command(no_pm=True)
    @checks.admin()
    async def inforemove(self, ctx, index):
        """Removes an entry."""
        screen = self.get_screen(ctx.guild.id)
        index = await self._validate_index(ctx, screen, index)
        if index is not None:
            del screen.elements[index]
            await ctx.send('The entry at index %d has been removed.' % (index + 1))
            await self.save_screens()

    @commands.command(no_pm=True)
    @checks.admin()
    async def infomove(self, ctx, index, new_index):
        """Moves an entry to a new index."""
        screen = self.get_screen(ctx.guild.id)
        index = await self._validate_index(ctx, screen, index)
        new_index = await self._validate_index(ctx, screen, new_index)
        if index is None or new_index is None:
            return

        element = screen.elements[index]
        del screen.elements[index]
        screen.elements.insert(new_index, element)
        await ctx.send('The entry at index %d was moved to index %d' % (index + 1, new_index + 1))
        await self.save_screens()

    @commands.command(no_pm=True)
    @checks.admin()
    async def infoswap(self, ctx, first_index, second_index):
        """Swaps an entry with another."""
        screen = self.get_screen(ctx.guild.id)
        first_index = await self._validate_index(ctx, screen, first_index)
        second_index = await self._validate_index(ctx, screen, second_index)
        if first_index is None or second_index is None:
            return

        tmp = screen.elements[first_index]
        screen.elements[first_index] = screen.elements[second_index]
        screen.elements[second_index] = tmp
        await ctx.send(
            'The entry at index %d has been swapped with the entry at index %d' % (
                first_index + 1, second_index + 1)
        )
        await self.save_screens()
