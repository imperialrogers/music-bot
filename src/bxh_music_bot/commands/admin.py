"""Administrative and setup slash commands."""

from typing import Annotated, TypeAlias
import os

from ..core import *
from ..helpers.common import *
from ..ui.controller import update_controller
import gc
import psutil  # type: ignore[import-untyped]

class FlexibleTextChannelTransformer(app_commands.Transformer):  # type: ignore[type-var]
    async def transform(self, interaction: discord.Interaction, value):
        if isinstance(value, discord.TextChannel):
            return value

        if isinstance(value, str) and interaction.guild:
            raw_value = value.strip()
            if raw_value.startswith("<#") and raw_value.endswith(">"):
                try:
                    channel_id = int(raw_value[2:-1])
                    channel = interaction.guild.get_channel(channel_id)
                    if isinstance(channel, discord.TextChannel):
                        return channel
                except ValueError:
                    pass

            raw_value = raw_value.lstrip("#")
            channel = discord.utils.get(
                interaction.guild.text_channels, name=raw_value
            )
            if channel:
                return channel

        raise app_commands.TransformerError(
            value,
            "channel",
            self,
        )

ChannelInput: TypeAlias = Annotated[
    discord.TextChannel,
    app_commands.Transform[discord.TextChannel, FlexibleTextChannelTransformer],
]

# /kaomoji command
@bot.tree.command(name="kaomoji", description="Enable/disable kawaii mode")
@app_commands.default_permissions(administrator=True)
async def toggle_kawaii(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message(
            get_messages("command.error.guild_only", interaction.guild_id),
            ephemeral=True,
            silent=SILENT_MESSAGES,
        )
        return

    guild_id = interaction.guild_id
    state = get_guild_state(guild_id)
    if state.locale == Locale.EN_X_KAWAII:
        state.locale = Locale.EN_US
    else:
        state.locale = Locale.EN_X_KAWAII
    state = (
        get_messages("kawaii_state_enabled", guild_id)
        if (get_guild_state(guild_id).locale == Locale.EN_X_KAWAII)
        else get_messages("kawaii_state_disabled", guild_id)
    )

    embed = Embed(
        description=get_messages("kawaii_toggle", guild_id, state=state),
        color=(
            0xFFB6C1
            if (get_guild_state(guild_id).locale == Locale.EN_X_KAWAII)
            else discord.Color.blue()
        ),
    )
    await interaction.response.send_message(
        silent=SILENT_MESSAGES, embed=embed, ephemeral=True
    )

@app_commands.default_permissions(administrator=True)
class SetupCommands(app_commands.Group):
    """Commands for setting up the bot on the server."""

    def __init__(self, bot: commands.Bot):
        super().__init__(
            name="setup",
            description="Set up bot features for the server.",
            default_permissions=discord.Permissions(administrator=True),
        )
        self.bot = bot

    @app_commands.command(
        name="controller",
        description="Sets a channel for the persistent music controller.",
    )
    @app_commands.describe(
        channel="The text channel for the controller. Defaults to the current channel if not specified."
    )
    async def controller(
        self,
        interaction: discord.Interaction,
        channel: Optional[ChannelInput] = None,
    ):
        """Sets or updates the channel for the music controller."""
        if not interaction.guild:
            await interaction.response.send_message(
                get_messages("command.error.guild_only", interaction.guild.id),
                ephemeral=True,
                silent=SILENT_MESSAGES,
            )
            return

        target_channel = channel or interaction.channel
        guild_id = interaction.guild.id

        if get_guild_state(guild_id).controller_message_id:
            try:
                old_channel_id = get_guild_state(guild_id).controller_channel_id
                if old_channel_id:
                    old_channel = self.bot.get_channel(old_channel_id)
                    if old_channel:
                        old_message = await old_channel.fetch_message(
                            get_guild_state(guild_id).controller_message_id
                        )
                        await old_message.delete()
                        logger.info(
                            f"Deleted old controller message in guild {guild_id}"
                        )
            except (discord.NotFound, discord.Forbidden):
                pass

        get_guild_state(guild_id).controller_channel_id = target_channel.id
        get_guild_state(guild_id).controller_message_id = None

        await interaction.response.send_message(
            get_messages(
                "setup.controller.success",
                guild_id,
                channel_mention=target_channel.mention,
            ),
            ephemeral=True,
            silent=SILENT_MESSAGES,
        )
        await update_controller(self.bot, guild_id)

    @app_commands.command(
        name="allowlist", description="Restricts bot commands to specific channels."
    )
    @app_commands.describe(
        reset="Type 'default' to allow commands in all channels again.",
        channel1="The first channel to allow.",
        channel2="An optional second channel to allow.",
        channel3="An optional third channel to allow.",
        channel4="An optional fourth channel to allow.",
        channel5="An optional fifth channel to allow.",
    )
    async def allowlist(
        self,
        interaction: discord.Interaction,
        reset: Optional[str] = None,
        channel1: Optional[ChannelInput] = None,
        channel2: Optional[ChannelInput] = None,
        channel3: Optional[ChannelInput] = None,
        channel4: Optional[ChannelInput] = None,
        channel5: Optional[ChannelInput] = None,
    ):

        guild_id = interaction.guild.id
        state = get_guild_state(guild_id)
        is_kawaii = state.locale == Locale.EN_X_KAWAII

        # Case 1: Reset the allowlist
        if reset and reset.lower() == "default":
            state = get_guild_state(guild_id)
            if state.allowed_channels:
                state.allowed_channels.clear()
                logger.info(
                    f"Command channel allowlist has been RESET for guild {guild_id}."
                )

            embed = discord.Embed(
                description=get_messages("setup.allowlist.reset_success", guild_id),
                color=0xB5EAD7 if is_kawaii else discord.Color.green(),
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True, silent=True
            )
            return

        # Case 2: Set the allowlist
        channels = [
            ch
            for ch in [channel1, channel2, channel3, channel4, channel5]
            if ch is not None
        ]

        if channels:
            allowed_ids = {ch.id for ch in channels}
            get_guild_state(guild_id).allowed_channels = allowed_ids

            channel_mentions = ", ".join([ch.mention for ch in channels])
            logger.info(
                f"Command channel allowlist for guild {guild_id} set to: {allowed_ids}"
            )

            embed = discord.Embed(
                description=get_messages(
                    "setup.allowlist.set_success", guild_id, channels=channel_mentions
                ),
                color=0xB5EAD7 if is_kawaii else discord.Color.green(),
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True, silent=True
            )
            return

        # Case 3: Invalid arguments
        embed = discord.Embed(
            description=get_messages("setup.allowlist.invalid_args", guild_id),
            color=0xFF9AA2 if is_kawaii else discord.Color.orange(),
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, silent=True
        )


# /gc command - Force garbage collection
@bot.tree.command(name="gc", description="Force garbage collection to free memory (Admin only)")
@app_commands.default_permissions(administrator=True)
async def force_gc(interaction: discord.Interaction):
    """Manually trigger garbage collection."""
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
            silent=SILENT_MESSAGES,
        )
        return
    
    guild_id = interaction.guild_id
    state = get_guild_state(guild_id)
    is_kawaii = state.locale == Locale.EN_X_KAWAII
    
    # Defer response as GC might take a moment
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Get memory before GC
        process = psutil.Process()
        mem_before = process.memory_info().rss / (1024 * 1024)
        
        # Run full garbage collection
        collected_gen0 = gc.collect(generation=0)
        collected_gen1 = gc.collect(generation=1)
        collected_gen2 = gc.collect(generation=2)
        total_collected = collected_gen0 + collected_gen1 + collected_gen2
        
        # Get memory after GC
        mem_after = process.memory_info().rss / (1024 * 1024)
        freed = mem_before - mem_after
        
        # Create response embed
        embed = Embed(
            title="🗑️ Garbage Collection Complete",
            description="Manual garbage collection has been executed.",
            color=0xB5EAD7 if is_kawaii else discord.Color.green(),
        )
        
        embed.add_field(
            name="Memory Before",
            value=f"{mem_before:.1f} MB",
            inline=True
        )
        
        embed.add_field(
            name="Memory After",
            value=f"{mem_after:.1f} MB",
            inline=True
        )
        
        embed.add_field(
            name="Memory Freed",
            value=f"{freed:.1f} MB" if freed > 0 else "0.0 MB",
            inline=True
        )
        
        embed.add_field(
            name="Objects Collected",
            value=f"Gen 0: {collected_gen0}\nGen 1: {collected_gen1}\nGen 2: {collected_gen2}\n**Total: {total_collected}**",
            inline=False
        )
        
        embed.set_footer(text="Garbage collection helps free unused memory")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Manual GC triggered by {interaction.user} in guild {guild_id}: Freed {freed:.1f} MB")
        
    except Exception as e:
        error_embed = Embed(
            title="❌ Error",
            description=f"Failed to run garbage collection: {str(e)}",
            color=0xFF9AA2 if is_kawaii else discord.Color.red(),
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
        logger.error(f"Error in /gc command: {e}")


# /memory command - Show memory statistics
@bot.tree.command(name="memory", description="Show current memory usage statistics (Admin only)")
@app_commands.default_permissions(administrator=True)
async def memory_stats(interaction: discord.Interaction):
    """Display current memory usage statistics."""
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
            silent=SILENT_MESSAGES,
        )
        return
    
    guild_id = interaction.guild_id
    state = get_guild_state(guild_id)
    is_kawaii = state.locale == Locale.EN_X_KAWAII
    
    try:
        # Get process memory info
        process = psutil.Process()
        mem_info = process.memory_info()
        current_mb = mem_info.rss / (1024 * 1024)
        
        # Memory limit (512MB)
        limit_mb = 512.0
        percent = (current_mb / limit_mb) * 100
        
        # Get thresholds from environment
        warning_threshold = float(os.getenv("MEMORY_WARNING_THRESHOLD", "70"))
        critical_threshold = float(os.getenv("MEMORY_CRITICAL_THRESHOLD", "85"))
        emergency_threshold = float(os.getenv("MEMORY_EMERGENCY_THRESHOLD", "95"))
        
        warning_mb = limit_mb * (warning_threshold / 100)
        critical_mb = limit_mb * (critical_threshold / 100)
        emergency_mb = limit_mb * (emergency_threshold / 100)
        
        # Determine status color and emoji
        if percent >= emergency_threshold:
            color = discord.Color.red()
            status_emoji = "🚨"
            status_text = "EMERGENCY"
        elif percent >= critical_threshold:
            color = discord.Color.orange()
            status_emoji = "🔶"
            status_text = "CRITICAL"
        elif percent >= warning_threshold:
            color = discord.Color.gold()
            status_emoji = "⚠️"
            status_text = "WARNING"
        else:
            color = 0xB5EAD7 if is_kawaii else discord.Color.green()
            status_emoji = "✅"
            status_text = "HEALTHY"
        
        # Get system memory
        system_mem = psutil.virtual_memory()
        system_total_mb = system_mem.total / (1024 * 1024)
        system_available_mb = system_mem.available / (1024 * 1024)
        
        # Get GC stats
        gc_stats = gc.get_stats()
        gc_count = gc.get_count()
        
        # Create embed
        embed = Embed(
            title=f"{status_emoji} Memory Statistics",
            description=f"**Status:** {status_text}",
            color=color,
        )
        
        # Bot memory usage
        embed.add_field(
            name="Bot Memory Usage",
            value=f"**{current_mb:.1f} MB** / {limit_mb:.0f} MB ({percent:.1f}%)",
            inline=False
        )
        
        # Progress bar
        bar_length = 20
        filled = int((percent / 100) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        embed.add_field(
            name="Usage Bar",
            value=f"`{bar}` {percent:.1f}%",
            inline=False
        )
        
        # Thresholds
        embed.add_field(
            name="Thresholds",
            value=f"⚠️ Warning: {warning_mb:.0f} MB ({warning_threshold}%)\n"
                  f"🔶 Critical: {critical_mb:.0f} MB ({critical_threshold}%)\n"
                  f"🚨 Emergency: {emergency_mb:.0f} MB ({emergency_threshold}%)",
            inline=False
        )
        
        # System memory
        embed.add_field(
            name="System Memory",
            value=f"Total: {system_total_mb:.0f} MB\n"
                  f"Available: {system_available_mb:.0f} MB\n"
                  f"Used: {system_mem.percent:.1f}%",
            inline=True
        )
        
        # GC info
        embed.add_field(
            name="Garbage Collector",
            value=f"Gen 0: {gc_count[0]} objects\n"
                  f"Gen 1: {gc_count[1]} objects\n"
                  f"Gen 2: {gc_count[2]} objects",
            inline=True
        )
        
        # Queue info
        music_player = state.music_player
        queue_size = music_player.queue.qsize() if music_player.queue else 0
        history_size = len(music_player.history) if music_player.history else 0
        
        embed.add_field(
            name="Bot State",
            value=f"Queue: {queue_size} items\n"
                  f"History: {history_size} items\n"
                  f"Connected: {'Yes' if music_player.voice_client else 'No'}",
            inline=True
        )
        
        embed.set_footer(text="Use /gc to manually free memory")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        error_embed = Embed(
            title="❌ Error",
            description=f"Failed to retrieve memory statistics: {str(e)}",
            color=0xFF9AA2 if is_kawaii else discord.Color.red(),
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        logger.error(f"Error in /memory command: {e}")
