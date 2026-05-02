"""Application assembly and runtime entrypoint for bxh-music-bot."""

from .core import *
from .models.lazy_search import *
from .helpers.common import *
from .helpers.url_utils import *
from .services.voice import *
from .ui.controller import *
from .services.playback import *
from .ui.interactions import *
from .services.lyrics import *
from .services.platforms import *
from .commands.music import *
from .commands.admin import *
from .health_server import run_health_server

if bot.tree.get_command("setup") is None:
    bot.tree.add_command(SetupCommands(bot))

from .events import *

def run():
    init_db()
    bot.start_time = time.time()
    
    # Start health check server for Render/hosting platforms
    run_health_server(bot_start_time=bot.start_time)
    
    bot.run(os.getenv("DISCORD_TOKEN"))
