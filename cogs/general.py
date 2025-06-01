import discord
from discord.ext import commands
from discord import app_commands
import collections
import logging
import datetime

logger = logging.getLogger("discord_bot")

# Assuming these are available from main.py via bot.
# You could also put these in a separate config.py and import them in each cog.
COMMAND_MENU = {
    "bags": {
        "description": "Calculates soulstone probabilities from bag draws.",
        "usage_prefix": "`!bags <bag I count> <bag II count> <target soulstones>`",
        "usage_slash": "`/bags bag1:<count> bag2:<count> ss:<target>`",
        "emoji": "💎",
        "has_args": True,
    },
    "baginfo": {
        "description": "Displays information about Bag I and Bag II contents and their average values.",
        "usage_prefix": "`!baginfo`",
        "usage_slash": "`/baginfo`",
        "emoji": "🛍️",
        "has_args": False,
    },
    "ping": {
        "description": "Checks the bot's latency.",
        "usage_prefix": "`!ping`",
        "usage_slash": "`/ping`",
        "emoji": "🏓",
        "has_args": False,
    },
    "info": {
        "description": "Displays general information about the bot.",
        "usage_prefix": "`!info`",
        "usage_slash": "`/info`",
        "emoji": "ℹ️",
        "has_args": False,
    },
    "menu": {
        "description": "Displays this command menu.",
        "usage_prefix": "`!menu`",
        "usage_slash": "`/menu`",
        "emoji": "📚",
        "has_args": False,
    },
}


# Helper functions for embeds (can be a separate 'embed_helpers.py')
async def create_info_embed(bot_instance: commands.Bot):
    owner_name = bot_instance.OWNER_DISPLAY_NAME
    if bot_instance.owner_id:
        try:
            owner = await bot_instance.fetch_user(bot_instance.owner_id)
            if owner:
                owner_name = owner.display_name
        except discord.NotFound:
            logger.warning(f"Owner with ID {bot_instance.owner_id} not found.")
        except discord.HTTPException as e:
            logger.error(f"Failed to fetch owner user: {e}")

    uptime_display = "Not available"
    if bot_instance.bot_online_since:
        timestamp = int(bot_instance.bot_online_since.timestamp())
        uptime_display = f"<t:{timestamp}:R>"

    embed = discord.Embed(
        title="🤖 About This Bot",
        description=(
            "This is a custom Discord bot designed to help users with "
            "various utility commands, specifically focused on game-related "
            "calculations and information. It's built to be interactive and user-friendly."
        ),
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(
        url=(
            bot_instance.user.avatar.url
            if bot_instance.user.avatar
            else discord.Embed.Empty
        )
    )
    embed.add_field(name="Owner", value=owner_name, inline=True)
    embed.add_field(
        name="Latency", value=f"{bot_instance.latency * 1000:.2f}ms", inline=True
    )
    embed.add_field(name="Uptime", value=uptime_display, inline=True)
    embed.add_field(name="Guilds", value=len(bot_instance.guilds), inline=True)
    embed.add_field(name="Users", value=len(bot_instance.users), inline=True)
    embed.add_field(
        name="Source Code",
        value="[View on GitHub](https://github.com/eve718/ccBot/commits/main/)",
        inline=False,
    )
    embed.add_field(
        name="Invite Bot",
        value="[Add to Your Server](https://discord.com/oauth2/authorize?client_id=1376302750056579112&permissions=2147503104&integration_type=0&scope=bot+applications.commands)",
        inline=False,
    )
    embed.set_footer(text="Thank you for using the bot!")
    return embed


async def create_ping_embed(bot_instance: commands.Bot):
    latency_ms = round(bot_instance.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: {latency_ms}ms",
        color=discord.Color.green(),
    )
    return embed


async def create_welcome_embed():
    embed = discord.Embed(
        title="Welcome to rngBot!",
        description="Select a command from the menu below to learn more or perform an action.",
        color=discord.Color.blue(),
    )
    return embed


async def create_menu_embed(bot_instance: commands.Bot):
    embed = discord.Embed(
        title="📚 Bot Commands Menu",
        description="Click a button below to learn more about a command or run it directly (if it has no arguments).",
        color=discord.Color.purple(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    for cmd_name, cmd_details in COMMAND_MENU.items():
        description = cmd_details.get("description", "No description available.")
        usage_prefix = cmd_details.get("usage_prefix", "N/A")
        usage_slash = cmd_details.get("usage_slash", "N/A")
        emoji = cmd_details.get("emoji", "")

        embed.add_field(
            name=f"{emoji} {cmd_name.capitalize()} Command",
            value=(
                f"{description}\n"
                f"**Prefix Usage:** {usage_prefix}\n"
                f"**Slash Usage:** {usage_slash}"
            ),
            inline=False,
        )

    embed.set_footer(
        text=f"Interact below! | Made by {bot_instance.OWNER_DISPLAY_NAME}"
    )
    return embed


class CommandMenuView(discord.ui.View):
    def __init__(self, bot_instance: commands.Bot, timeout=300):
        super().__init__(timeout=timeout)
        self.bot_instance = bot_instance
        self.message = None

    @discord.ui.button(
        label="Info", custom_id="menu_button_info", style=discord.ButtonStyle.primary
    )
    async def info_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_button_click(interaction, button)

    @discord.ui.button(
        label="Bag Info",
        custom_id="menu_button_baginfo",
        style=discord.ButtonStyle.primary,
    )
    async def baginfo_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_button_click(interaction, button)

    @discord.ui.button(
        label="Bags (Input Args)",
        custom_id="menu_button_bags",
        style=discord.ButtonStyle.secondary,
    )
    async def bags_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_button_click(interaction, button)

    @discord.ui.button(
        label="Ping", custom_id="menu_button_ping", style=discord.ButtonStyle.primary
    )
    async def ping_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_button_click(interaction, button)

    async def _handle_button_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            await interaction.response.defer(ephemeral=False, thinking=True)
            command_name = button.custom_id.replace("menu_button_", "")
            logger.info(f"User {interaction.user.id} clicked '{command_name}' button.")

            content_embed = None
            current_view = self

            # Dynamically fetch commands using bot.get_command or bot.tree.get_command
            # This makes the menu robust even if commands are unloaded.
            if command_name == "info":
                content_embed = await create_info_embed(self.bot_instance)
            elif command_name == "ping":
                content_embed = await create_ping_embed(self.bot_instance)
            elif command_name == "baginfo":
                # Need to import/access baginfo_embed function. This implies
                # embed helpers should be central or passed explicitly.
                # For simplicity, I'm assuming it's available or moved to a common helper.
                # If baginfo_embed is in bags.py, it needs to be imported or refactored.
                # For this example, let's assume all embed creators are available here or imported.
                # A cleaner way: pass a dictionary of embed creators to the view.
                # For now, let's just make `create_baginfo_embed` available in this scope.
                # We will need to make this function available from 'bags.py'
                # For the sake of this example, we'll refactor baginfo_embed into general.py if it's generic enough.
                # OR, the menu itself would be a class that has access to all command methods.
                # For now, if the menu directly creates embeds, it needs access to the data/funcs.
                # The create_baginfo_embed relies on BAG_I_DEFINITION etc. which are now on bot.
                from cogs.bags import create_baginfo_embed

                content_embed = await create_baginfo_embed(self.bot_instance)
            elif command_name == "bags":
                content_embed = discord.Embed(
                    title=f"Usage for /{command_name}",
                    description=f"The `/{command_name}` command requires arguments. Please type `/{command_name}` and follow the prompts.",
                    color=discord.Color.yellow(),
                )
            else:
                content_embed = discord.Embed(
                    title="Command Not Found",
                    description="This command is not recognized or not yet implemented in the interactive menu.",
                    color=discord.Color.red(),
                )

            if self.message:
                await self.message.edit(embed=content_embed, view=current_view)
                logger.info(f"Edited menu embed for command '{command_name}'.")
            else:
                logger.warning(
                    f"Failed to edit menu embed for '{command_name}': self.message was not set."
                )
                await interaction.followup.send(embed=content_embed, ephemeral=True)
                return

            await interaction.delete_original_response()
            logger.info(
                f"Dismissed 'Bot is thinking...' message for '{command_name}' button click."
            )

        except Exception as e:
            logger.error(
                f"UNCAUGHT ERROR during menu button click (custom_id: {button.custom_id}): {e}",
                exc_info=True,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred while processing your request. The bot owner has been notified.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "An unexpected error occurred after starting your request. The bot owner has been notified.",
                    ephemeral=True,
                )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
                logger.info("Menu view timed out and buttons disabled.")
            except discord.NotFound:
                logger.warning(
                    "Tried to edit timed-out menu message, but it was not found."
                )
            except Exception as e:
                logger.error(f"Error editing timed-out menu message: {e}")
        else:
            logger.warning(
                "Menu view timed out but message attribute was not set, cannot disable buttons."
            )


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", description="Checks the bot's latency.")
    async def ping_prefix(self, ctx):
        logger.info(f"Prefix command 'ping' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            embed = await create_ping_embed(self.bot)
            await ctx.send(embed=embed)
            logger.info(f"Sent ping response to {ctx.author.id}.")

    @app_commands.command(name="ping", description="Checks the bot's latency.")
    async def ping_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'ping' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        embed = await create_ping_embed(self.bot)
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent ping response to {interaction.user.id}.")

    @commands.command(
        name="info", description="Displays general information about the bot."
    )
    async def info_prefix(self, ctx):
        logger.info(f"Prefix command 'info' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            embed = await create_info_embed(self.bot)
            await ctx.send(embed=embed)
            logger.info(f"Sent info response to {ctx.author.id}.")

    @app_commands.command(
        name="info", description="Displays general information about the bot."
    )
    async def info_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'info' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        embed = await create_info_embed(self.bot)
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent info response to {interaction.user.id}.")

    @commands.command(name="menu", description="Displays a list of available commands.")
    async def menu_prefix(self, ctx):
        logger.info(f"Prefix command 'menu' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            initial_embed = await create_welcome_embed()
            view = CommandMenuView(bot_instance=self.bot)
            message = await ctx.send(embed=initial_embed, view=view)
            view.message = message
            logger.info(f"Sent menu response to {ctx.author.id}.")

    @app_commands.command(
        name="menu", description="Displays a list of available commands."
    )
    async def menu_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'menu' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        initial_embed = await create_welcome_embed()
        view = CommandMenuView(bot_instance=self.bot)
        message = await interaction.followup.send(embed=initial_embed, view=view)
        view.message = message
        logger.info(f"Sent menu response to {interaction.user.id}.")


async def setup(bot):
    await bot.add_cog(General(bot))
