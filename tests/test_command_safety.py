import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

# Ensure the src package is importable for tests.
ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import py_compile
from discord import app_commands
import bxh_music_bot.events as events


class TestBxhMusicBotImports(unittest.TestCase):
    def test_bxh_music_bot_modules_import(self):
        import importlib

        importlib.import_module("bxh_music_bot.commands.music")
        importlib.import_module("bxh_music_bot.commands.admin")
        importlib.import_module("bxh_music_bot.events")


class TestGlobalSlashCommandErrorHandler(unittest.IsolatedAsyncioTestCase):
    async def test_on_global_app_command_error_uses_response(self):
        interaction = Mock()
        interaction.response = Mock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.followup = Mock()

        error = app_commands.CommandInvokeError(Mock(), Exception("test"))
        await events.on_global_app_command_error(interaction, error)

        interaction.response.send_message.assert_called_once_with(
            content="An unexpected error occurred while processing this command. Please try again later.",
            ephemeral=True,
        )
        interaction.followup.send.assert_not_called()

    async def test_on_global_app_command_error_uses_followup_when_response_done(self):
        interaction = Mock()
        interaction.response = Mock()
        interaction.response.is_done.return_value = True
        interaction.response.send_message = AsyncMock()
        interaction.followup = Mock()
        interaction.followup.send = AsyncMock()

        error = app_commands.CommandInvokeError(Mock(), Exception("test"))
        await events.on_global_app_command_error(interaction, error)

        interaction.followup.send.assert_called_once_with(
            content="An unexpected error occurred while processing this command. Please try again later.",
            ephemeral=True,
        )
        interaction.response.send_message.assert_not_called()


class TestCompileAllSourceFiles(unittest.TestCase):
    def test_compile_all_source_files(self):
        for path in sorted(SRC_DIR.rglob("*.py")):
            py_compile.compile(str(path), doraise=True)
