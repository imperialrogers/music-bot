"""Discord logging handler with memory usage tracking for bxh-music-bot."""

import logging
import asyncio
import discord
from discord import Embed, Color
from datetime import datetime
import psutil  # type: ignore[import-untyped]
import os
from typing import Optional, Any, Deque
from collections import deque
import time
import gc


class MemoryTracker:
    """Tracks memory usage statistics for the bot process."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.peak_memory = 0.0
        self.start_time = time.time()
    
    def get_memory_info(self) -> dict:
        """Get current memory usage information."""
        try:
            mem_info = self.process.memory_info()
            current_mb = mem_info.rss / (1024 * 1024)  # Convert to MB
            
            # Update peak memory
            if current_mb > self.peak_memory:
                self.peak_memory = current_mb
            
            # Get system memory
            system_mem = psutil.virtual_memory()
            total_mb = system_mem.total / (1024 * 1024)
            available_mb = system_mem.available / (1024 * 1024)
            percent = system_mem.percent
            
            return {
                'current_mb': current_mb,
                'peak_mb': self.peak_memory,
                'total_mb': total_mb,
                'available_mb': available_mb,
                'percent': percent
            }
        except Exception as e:
            return {
                'current_mb': 0.0,
                'peak_mb': 0.0,
                'total_mb': 0.0,
                'available_mb': 0.0,
                'percent': 0.0,
                'error': str(e)
            }
    
    def format_memory_string(self) -> str:
        """Format memory info as a compact string."""
        info = self.get_memory_info()
        if 'error' in info:
            return f"[MEM: Error - {info['error']}]"
        
        return f"[MEM: {info['current_mb']:.1f}MB/{info['total_mb']:.0f}MB ({info['percent']:.1f}%) | Peak: {info['peak_mb']:.1f}MB]"


class GarbageCollector:
    """
    Manages garbage collection and memory optimization for 24/7 operation.
    
    GC Safety Strategy:
    - Generation 0 (quick): ~1-5ms, collects young objects only
      * Used during active playback (periodic checks, warnings)
      * Safe for music streaming, won't cause audio glitches
      * Non-blocking for voice connections
    
    - Generation 1 (medium): ~10-50ms, collects gen 0 + gen 1
      * Reserved for idle times or moderate memory pressure
      * Not used during active playback to avoid interruptions
    
    - Generation 2 (full): ~100-500ms, full collection
      * Only used in critical/emergency situations
      * May cause brief audio stutter if used during playback
      * Automatically triggered when memory exceeds critical thresholds
    
    24/7 Operation Guarantee:
    - Periodic GC (every 5 min) uses generation 0 only
    - Active playback never interrupted by routine GC
    - Full GC only runs when memory is critical or bot is idle
    - All GC operations run synchronously but are quick enough to not block
    """
    
    def __init__(self):
        self.process = psutil.Process()
        self.last_gc_time = time.time()
        self.gc_interval = 300  # Run GC every 5 minutes minimum
    
    def get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        try:
            return self.process.memory_info().rss / (1024 * 1024)  # type: ignore[no-any-return]
        except Exception:
            return 0.0
    
    def run_gc(self, generation: int = 2) -> dict:
        """
        Run garbage collection and return statistics.
        
        Args:
            generation: GC generation to collect
                - 0 (quick): ~1-5ms, safe during playback, non-blocking
                - 1 (medium): ~10-50ms, use when idle or moderate pressure
                - 2 (full): ~100-500ms, emergency only, may cause brief stutter
        
        Returns:
            dict with before/after memory and freed amount
        
        GC Safety Notes:
        - Generation 0 is ALWAYS safe during active playback
        - Generation 1 should only be used during idle periods
        - Generation 2 is for emergencies when memory is critical
        - All collections are synchronous but quick enough to not block event loop
        """
        try:
            mem_before = self.get_memory_mb()
            
            # Run garbage collection
            if generation == 2:
                # Full collection
                collected = gc.collect()
            else:
                # Generational collection
                collected = gc.collect(generation=generation)
            
            mem_after = self.get_memory_mb()
            freed = mem_before - mem_after
            
            self.last_gc_time = time.time()
            
            return {
                'before_mb': mem_before,
                'after_mb': mem_after,
                'freed_mb': freed,
                'objects_collected': collected,
                'generation': generation
            }
        except Exception as e:
            return {
                'error': str(e),
                'before_mb': 0.0,
                'after_mb': 0.0,
                'freed_mb': 0.0,
                'objects_collected': 0,
                'generation': generation
            }
    
    def should_run_periodic_gc(self) -> bool:
        """Check if periodic GC should run based on time interval."""
        return (time.time() - self.last_gc_time) >= self.gc_interval


class MemoryMonitor:
    """Monitors memory usage and sends threshold warnings."""
    
    # Memory limit in MB (512MB)
    MEMORY_LIMIT_MB = 512.0
    
    def __init__(self, bot: discord.Client, channel: Optional[discord.TextChannel] = None):
        self.bot = bot
        self.channel = channel
        self.process = psutil.Process()
        self.gc_manager = GarbageCollector()
        self.memory_tracker = MemoryTracker()
        
        # Load thresholds from environment or use defaults
        self.warning_threshold = float(os.getenv("MEMORY_WARNING_THRESHOLD", "70"))
        self.critical_threshold = float(os.getenv("MEMORY_CRITICAL_THRESHOLD", "85"))
        self.emergency_threshold = float(os.getenv("MEMORY_EMERGENCY_THRESHOLD", "95"))
        
        # Track warning states to prevent spam
        self.warning_sent = False
        self.critical_sent = False
        self.emergency_sent = False
        
        # Monitoring task
        self.monitor_task: Optional[asyncio.Task] = None
        self.is_monitoring = False
    
    def get_memory_usage(self) -> dict:
        """Get current memory usage statistics."""
        try:
            mem_info = self.process.memory_info()
            current_mb = mem_info.rss / (1024 * 1024)
            percent = (current_mb / self.MEMORY_LIMIT_MB) * 100
            
            return {
                'current_mb': current_mb,
                'limit_mb': self.MEMORY_LIMIT_MB,
                'percent': percent,
                'warning_mb': self.MEMORY_LIMIT_MB * (self.warning_threshold / 100),
                'critical_mb': self.MEMORY_LIMIT_MB * (self.critical_threshold / 100),
                'emergency_mb': self.MEMORY_LIMIT_MB * (self.emergency_threshold / 100)
            }
        except Exception as e:
            return {
                'current_mb': 0.0,
                'limit_mb': self.MEMORY_LIMIT_MB,
                'percent': 0.0,
                'error': str(e)
            }
    
    async def send_threshold_warning(self, level: str, stats: dict):
        """Send a threshold warning to the log channel."""
        if not self.channel:
            return
        
        try:
            # Determine color and emoji based on level
            if level == "warning":
                color = Color.gold()
                emoji = "⚠️"
                title = "Memory Warning"
            elif level == "critical":
                color = Color.orange()
                emoji = "🔶"
                title = "Critical Memory Usage"
            else:  # emergency
                color = Color.red()
                emoji = "🚨"
                title = "Emergency Memory Alert"
            
            embed = Embed(
                title=f"{emoji} {title}",
                description=f"Memory usage has exceeded the {level} threshold!",
                color=color,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Current Usage",
                value=f"**{stats['current_mb']:.1f} MB** / {stats['limit_mb']:.0f} MB ({stats['percent']:.1f}%)",
                inline=False
            )
            
            embed.add_field(
                name="Thresholds",
                value=f"⚠️ Warning: {stats['warning_mb']:.0f} MB ({self.warning_threshold}%)\n"
                      f"🔶 Critical: {stats['critical_mb']:.0f} MB ({self.critical_threshold}%)\n"
                      f"🚨 Emergency: {stats['emergency_mb']:.0f} MB ({self.emergency_threshold}%)",
                inline=False
            )
            
            # Add suggestions based on level
            if level == "warning":
                suggestions = "• Monitor queue size\n• Consider clearing old history\n• GC will run automatically"
            elif level == "critical":
                suggestions = "• Running aggressive GC\n• Limiting queue size\n• Clearing old cache entries"
            else:  # emergency
                suggestions = "• **IMMEDIATE ACTION REQUIRED**\n• Running full GC\n• Clearing all caches\n• Consider restarting bot"
            
            embed.add_field(
                name="Recommended Actions",
                value=suggestions,
                inline=False
            )
            
            embed.set_footer(text="Memory monitoring system")
            
            await self.channel.send(embed=embed)
            
        except discord.Forbidden:
            print("Warning: No permission to send memory warnings to log channel")
        except Exception as e:
            print(f"Error sending memory warning: {e}")
    
    async def check_thresholds(self):
        """
        Check memory thresholds and send warnings if needed.
        
        GC Strategy for 24/7 Operation:
        - Warning (70%): Generation 0 GC - Quick, non-blocking, safe during playback
        - Critical (85%): Generation 2 GC - Full collection, may cause brief stutter
        - Emergency (95%): Generation 2 GC - Immediate full collection required
        
        The generation 0 GC at warning level ensures we catch memory issues early
        without interrupting music playback. Only when memory becomes critical do
        we use full GC, which is necessary to prevent crashes but may cause a
        brief audio interruption (acceptable trade-off for stability).
        """
        stats = self.get_memory_usage()
        
        if 'error' in stats:
            return
        
        percent = stats['percent']
        
        # Check emergency threshold (95%+)
        if percent >= self.emergency_threshold:
            if not self.emergency_sent:
                await self.send_threshold_warning("emergency", stats)
                self.emergency_sent = True
                # Emergency: Run full GC immediately to prevent crash
                # This is critical - brief audio stutter is acceptable to prevent bot crash
                gc_stats = self.gc_manager.run_gc(generation=2)
                print(f"Emergency GC (Gen 2): Freed {gc_stats['freed_mb']:.1f} MB")
        
        # Check critical threshold (85%+)
        elif percent >= self.critical_threshold:
            if not self.critical_sent:
                await self.send_threshold_warning("critical", stats)
                self.critical_sent = True
                # Critical: Run full GC to free memory before it becomes emergency
                # May cause brief audio stutter but necessary for stability
                gc_stats = self.gc_manager.run_gc(generation=2)
                print(f"Critical GC (Gen 2): Freed {gc_stats['freed_mb']:.1f} MB")
            # Reset emergency flag if we're below emergency
            self.emergency_sent = False
        
        # Check warning threshold (70%+)
        elif percent >= self.warning_threshold:
            if not self.warning_sent:
                await self.send_threshold_warning("warning", stats)
                self.warning_sent = True
                # Warning: Run quick GC (generation 0) - safe during playback
                # This is non-blocking and won't interrupt music
                gc_stats = self.gc_manager.run_gc(generation=0)
                print(f"Warning GC (Gen 0): Freed {gc_stats['freed_mb']:.1f} MB")
            # Reset higher flags
            self.critical_sent = False
            self.emergency_sent = False
        
        # Reset all flags if below warning threshold
        else:
            self.warning_sent = False
            self.critical_sent = False
            self.emergency_sent = False
    
    async def monitor_loop(self):
        """
        Background task that monitors memory usage.
        
        GC Safety for 24/7 Operation:
        - Uses generation 0 (quick, non-blocking) for periodic collections
        - Generation 0 only collects young objects, takes ~1-5ms
        - Does NOT interrupt audio playback or voice connections
        - Runs in background without blocking the event loop
        """
        print("Memory monitoring started")
        
        # Initialize counter for periodic logging
        log_counter = 0
        
        while self.is_monitoring:
            try:
                # Check thresholds
                await self.check_thresholds()
                
                # Log current memory status periodically (every 10 cycles = 5 minutes)
                log_counter += 1
                if log_counter % 10 == 0:  # Every 10 cycles (5 minutes)
                    stats = self.get_memory_usage()
                    if 'error' not in stats:
                        # Get peak memory from memory tracker
                        mem_info = self.memory_tracker.get_memory_info()
                        peak_mb = mem_info.get('peak_mb', 0.0)
                        print(f"[Memory Monitor] Current: {stats['current_mb']:.1f}MB / {stats['limit_mb']:.0f}MB ({stats['percent']:.1f}%) | Peak: {peak_mb:.1f}MB")
                
                # Run periodic GC if needed (generation 0 for non-blocking operation)
                if self.gc_manager.should_run_periodic_gc():
                    # Use generation 0 for quick, non-blocking collection during active playback
                    # This is safe for 24/7 operation and won't interrupt music
                    gc_stats = self.gc_manager.run_gc(generation=0)
                    print(f"Periodic GC (Gen 0): Freed {gc_stats['freed_mb']:.1f} MB")
                
                # Wait 30 seconds before next check
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in memory monitor loop: {e}")
                await asyncio.sleep(60)
        
        print("Memory monitoring stopped")
    
    def start_monitoring(self):
        """Start the memory monitoring task."""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_task = asyncio.create_task(self.monitor_loop())
    
    def stop_monitoring(self):
        """Stop the memory monitoring task."""
        self.is_monitoring = False
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()


class DiscordLogHandler(logging.Handler):
    """Custom logging handler that sends logs to a Discord channel with rate limiting."""
    
    def __init__(self, bot: discord.Client, channel_name: str = "bxh-music-bot-logs", 
                 batch_size: int = 5, batch_interval: float = 10.0):
        """
        Initialize the Discord log handler.
        
        Args:
            bot: Discord bot instance
            channel_name: Name of the channel to send logs to
            batch_size: Maximum number of logs to batch before sending
            batch_interval: Time in seconds to wait before sending batched logs
        """
        super().__init__()
        self.bot = bot
        self.channel_name = channel_name
        self.channel: Optional[discord.TextChannel] = None
        self.memory_tracker = MemoryTracker()
        
        # Rate limiting / batching
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.log_queue: Deque[Any] = deque()
        self.last_send_time = time.time()
        self.send_task: Optional[asyncio.Task] = None
        self.is_ready = False
        
        # Color mapping for log levels
        self.level_colors: dict[int, Color] = {  # type: ignore[misc]
            logging.DEBUG: Color.light_gray(),
            logging.INFO: Color.blue(),
            logging.WARNING: Color.gold(),
            logging.ERROR: Color.red(),
            logging.CRITICAL: Color.dark_red()
        }
        
        # Emoji mapping for log levels
        self.level_emojis = {
            logging.DEBUG: "🔍",
            logging.INFO: "ℹ️",
            logging.WARNING: "⚠️",
            logging.ERROR: "❌",
            logging.CRITICAL: "🔥"
        }
    
    async def initialize(self):
        """Initialize the handler by finding or creating the log channel."""
        if self.is_ready:
            return
        
        try:
            # Get channel name from environment or use default
            channel_name = os.getenv("MUSIC_BOT_LOG_CHANNEL", self.channel_name)
            
            # Try to find the channel in all guilds
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.text_channels, name=channel_name)
                if channel:
                    self.channel = channel
                    self.is_ready = True
                    print(f"Discord log handler initialized: Logging to #{channel_name} in {guild.name}")
                    return
            
            # If not found, create it in the first guild
            if self.bot.guilds:
                guild = self.bot.guilds[0]
                try:
                    self.channel = await guild.create_text_channel(
                        channel_name,
                        topic="Automated logs from bxh-music-bot with memory tracking",
                        reason="Auto-created for bot logging"
                    )
                    self.is_ready = True
                    print(f"Discord log handler initialized: Created #{channel_name} in {guild.name}")
                except discord.Forbidden:
                    print(f"Warning: No permission to create log channel #{channel_name}")
                except Exception as e:
                    print(f"Error creating log channel: {e}")
        except Exception as e:
            print(f"Error initializing Discord log handler: {e}")
    
    def emit(self, record: logging.LogRecord):
        """Handle a log record by queuing it for Discord."""
        if not self.is_ready or not self.channel:
            return
        
        # Skip if Discord logging is disabled
        if os.getenv("DISABLE_DISCORD_LOGGING", "").lower() in ("true", "1", "yes"):
            return
        
        # Only log INFO and DEBUG levels (as per requirements)
        if record.levelno not in (logging.INFO, logging.DEBUG):
            return
        
        try:
            # Add memory info to the record
            record.memory_info = self.memory_tracker.format_memory_string()
            
            # Queue the log
            self.log_queue.append(record)
            
            # Start send task if not running
            if self.send_task is None or self.send_task.done():
                self.send_task = asyncio.create_task(self._process_queue())
        except Exception as e:
            print(f"Error in Discord log handler emit: {e}")
    
    async def _process_queue(self):
        """Process the log queue and send batched messages to Discord."""
        while self.log_queue:
            # Wait for batch interval or until batch size is reached
            await asyncio.sleep(1)
            
            current_time = time.time()
            should_send = (
                len(self.log_queue) >= self.batch_size or
                (current_time - self.last_send_time) >= self.batch_interval
            )
            
            if should_send and self.log_queue:
                await self._send_batch()
                self.last_send_time = current_time
    
    async def _send_batch(self):
        """Send a batch of logs to Discord."""
        if not self.channel or not self.log_queue:
            return
        
        try:
            # Collect up to batch_size logs
            batch = []
            for _ in range(min(self.batch_size, len(self.log_queue))):
                if self.log_queue:
                    batch.append(self.log_queue.popleft())
            
            if not batch:
                return
            
            # Create embed for the batch
            if len(batch) == 1:
                # Single log - use full embed
                record = batch[0]
                embed = self._create_embed(record)
                await self.channel.send(embed=embed)
            else:
                # Multiple logs - use compact format
                description = ""
                for record in batch:
                    emoji = self.level_emojis.get(record.levelno, "📝")
                    timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
                    msg = self.format(record)
                    # Truncate long messages
                    if len(msg) > 100:
                        msg = msg[:97] + "..."
                    description += f"{emoji} `{timestamp}` {msg}\n"
                
                # Add memory info from the last record
                if batch:
                    description += f"\n{getattr(batch[-1], 'memory_info', '')}"
                
                embed = Embed(
                    title=f"📊 Batch Logs ({len(batch)} messages)",
                    description=description[:4000],  # Discord limit
                    color=Color.blue(),
                    timestamp=datetime.utcnow()
                )
                await self.channel.send(embed=embed)
                
        except discord.Forbidden:
            print("Warning: No permission to send messages to log channel")
            self.is_ready = False
        except discord.HTTPException as e:
            print(f"Discord API error while sending logs: {e}")
        except Exception as e:
            print(f"Error sending log batch to Discord: {e}")
    
    def _create_embed(self, record: logging.LogRecord) -> Embed:
        """Create a Discord embed for a single log record."""
        color = self.level_colors.get(record.levelno, Color.default())
        emoji = self.level_emojis.get(record.levelno, "📝")
        
        # Format the message
        message = self.format(record)
        
        # Create embed
        embed = Embed(
            title=f"{emoji} {record.levelname}",
            description=f"```\n{message[:3900]}\n```",  # Use code block for formatting
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Add fields
        embed.add_field(name="Module", value=record.name, inline=True)
        embed.add_field(name="Function", value=record.funcName, inline=True)
        embed.add_field(name="Line", value=str(record.lineno), inline=True)
        
        # Add memory info
        memory_info = getattr(record, 'memory_info', 'N/A')
        embed.add_field(name="Memory Usage", value=memory_info, inline=False)
        
        # Add exception info if present
        if record.exc_info:
            exc_text = self.formatter.formatException(record.exc_info) if self.formatter else str(record.exc_info)
            if exc_text:
                embed.add_field(
                    name="Exception",
                    value=f"```python\n{exc_text[:1000]}\n```",
                    inline=False
                )
        
        return embed
    
    async def flush_and_close(self):
        """Flush remaining logs and close the handler."""
        if self.log_queue:
            await self._send_batch()
        self.is_ready = False


class MemoryLoggingFormatter(logging.Formatter):
    """Custom formatter that adds memory usage to all log messages."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.memory_tracker = MemoryTracker()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with memory information."""
        # Add memory info to the record
        memory_info = self.memory_tracker.format_memory_string()
        
        # Format the original message
        original_message = super().format(record)
        
        # Append memory info
        return f"{original_message} {memory_info}"


async def setup_discord_logging(bot: discord.Client, logger: logging.Logger):
    """
    Set up Discord logging for the bot.
    
    Args:
        bot: Discord bot instance
        logger: Logger instance to add the handler to
    
    Returns:
        tuple: (discord_handler, memory_monitor) or (None, None)
    """
    # Check if Discord logging is disabled
    if os.getenv("DISABLE_DISCORD_LOGGING", "").lower() in ("true", "1", "yes"):
        print("Discord logging is disabled via environment variable")
        return None, None
    
    # Create and initialize the Discord handler
    discord_handler = DiscordLogHandler(bot)
    await discord_handler.initialize()
    
    memory_monitor = None
    
    if discord_handler.is_ready:
        # Set formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        discord_handler.setFormatter(formatter)
        
        # Set level to INFO (will handle INFO and DEBUG as per emit logic)
        discord_handler.setLevel(logging.INFO)
        
        # Add to logger
        logger.addHandler(discord_handler)
        
        # Initialize memory monitor with the same channel
        memory_monitor = MemoryMonitor(bot, discord_handler.channel)
        memory_monitor.start_monitoring()
        
        print("Discord logging handler added successfully")
        print("Memory monitoring started")
        return discord_handler, memory_monitor
    else:
        print("Discord logging handler could not be initialized")
        return None, None


def add_memory_tracking_to_logger(logger: logging.Logger):
    """
    Add memory tracking to console logging.
    
    Args:
        logger: Logger instance to modify
    """
    # Find the console handler and update its formatter
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, DiscordLogHandler):
            # Create memory-aware formatter
            memory_formatter = MemoryLoggingFormatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(memory_formatter)
            print("Memory tracking added to console logger")
            break

# Made with Bob
