# cogs/general.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import datetime

# Import COMMAND_MENU from config.py
from config import COMMAND_MENU

logger = logging.getLogger("discord_bot")


async def create_welcome_embed():
    embed = discord.Embed(
        title="🤖 Welcome to the Command Menu!",
        description=(
            "Use the buttons below to navigate through different command categories. "
            "Click on a category to see its commands and usage instructions.\n\n"
            "**General Help:** If you need assistance with the bot or have questions, feel free to ask!"
        ),
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(
        url="https://cdn.discordapp.com/attachments/1098656123019085885/1246241315668613140/rngBot.png?ex=666113b9&is=665fc239&hm=70a0d9f0b18206d289196b996160893026210f9a566580556e9c20a4b3f89025&"
    )  # Consider using bot.user.display_avatar.url here if available
    return embed


async def create_info_embed(bot_instance: commands.Bot):
    # Retrieve data from bot instance
    uptime = discord.utils.utcnow() - bot_instance.bot_online_since
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    owner_name = getattr(
        bot_instance, "owner_display_name", "Bot Owner"
    )  # Use owner_display_name

    embed = discord.Embed(
        title="ℹ️ Bot Information",
        description="A versatile bot designed to provide useful utilities and calculations.",
        color=discord.Color.blurple(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    embed.add_field(name="🌐 Guilds", value=len(bot_instance.guilds), inline=True)
    embed.add_field(
        name="👥 Users", value=len(bot_instance.users), inline=True
    )  # This might be inaccurate without specific intents
    embed.add_field(
        name="🔗 Latency", value=f"{bot_instance.latency * 1000:.2f}ms", inline=True
    )
    embed.add_field(
        name="⏰ Uptime",
        value=f"{hours}h {minutes}m {seconds}s",
        inline=True,
    )
    embed.add_field(name="👑 Owner", value=owner_name, inline=True)
    embed.add_field(
        name="🐍 Python Version",
        value="3.10+",
        inline=True,
    )  # Consider using platform.python_version()
    embed.add_field(
        name="📚 discord.py Version",
        value=discord.__version__,
        inline=True,
    )
    embed.set_footer(
        text=f"Information provided by {bot_instance.user.name} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )  # Consistent footer format
    return embed


class CommandMenuView(discord.ui.View):
    def __init__(self, bot_instance, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot_instance
        self.message = None  # To store the message object for editing

        # Create buttons dynamically from COMMAND_MENU
        for category, data in COMMAND_MENU.items():
            if category != "owner":  # Don't add owner to public menu
                button = discord.ui.Button(
                    label=category.capitalize(),
                    style=discord.ButtonStyle.primary,
                    emoji=data.get("emoji"),
                    custom_id=f"menu_category_{category}",
                )
                button.callback = self.button_callback
                self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        category = interaction.custom_id.replace("menu_category_", "")
        command_data = COMMAND_MENU.get(category)

        if command_data:
            embed = discord.Embed(
                title=f"{command_data.get('emoji', '')} {category.capitalize()} Commands",
                description=f"**Description:** {command_data['description']}\n\n"
                f"**Prefix Usage:** {command_data['usage_prefix']}\n"
                f"**Slash Usage:** {command_data['usage_slash']}",
                color=discord.Color.green(),
            )
            embed.set_footer(
                text=f"Navigate the menu using the buttons below | {interaction.user.name}"
            )

            # Update the original message with the new embed
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.send_message(
                "Invalid category selected.", ephemeral=True
            )

    @discord.ui.button(
        label="Main Menu", style=discord.ButtonStyle.secondary, custom_id="menu_main"
    )
    async def main_menu_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        initial_embed = await create_welcome_embed()
        await interaction.response.edit_message(embed=initial_embed)

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)
            logger.info(f"Command menu timed out for message {self.message.id}.")

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ):
        logger.error(f"Error in command menu view: {error}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while interacting with the menu.", ephemeral=True
        )


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", description="Checks the bot's latency.")
    async def ping_prefix(self, ctx):
        logger.info(f"Prefix command 'ping' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            latency = self.bot.latency * 1000  # Convert to milliseconds
            await ctx.send(f"Pong! 🏓 `{latency:.2f}ms`")
            logger.info(f"Sent ping response to {ctx.author.id}.")

    @app_commands.command(name="ping", description="Checks the bot's latency.")
    async def ping_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'ping' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(
                ephemeral=False, thinking=True
            )  # Added thinking=True

        latency = self.bot.latency * 1000
        await interaction.followup.send(f"Pong! 🏓 `{latency:.2f}ms`")
        logger.info(f"Sent ping response to {interaction.user.id}.")

    @commands.command(
        name="info", description="Displays general information about the bot."
    )
    async def info_prefix(self, ctx):
        logger.info(f"Prefix command 'info' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            embed = await create_info_embed(self.bot)  # Pass bot instance
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
            await interaction.response.defer(
                ephemeral=False, thinking=True
            )  # Added thinking=True

        embed = await create_info_embed(self.bot)  # Pass bot instance
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
