"""Lightweight HTTP health check server for preventing Render spin-down."""

import json
import logging
import os
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

try:
    import requests  # type: ignore[import-untyped]
except ImportError:
    requests = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoints."""
    
    # Class variable to store bot start time
    bot_start_time = None
    
    def log_message(self, format, *args):
        """Override to use our logger instead of printing to stderr."""
        logger.info(f"Health check: {format % args}")
    
    def _set_headers(self, content_type="text/plain", status=200):
        """Set common response headers."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests to various endpoints."""
        if self.path == "/" or self.path == "/health":
            self._handle_health()
        elif self.path == "/ping":
            self._handle_ping()
        elif self.path == "/status":
            self._handle_status()
        else:
            self._handle_not_found()
    
    def _handle_health(self) -> None:
        """Handle /health endpoint - returns JSON with bot status."""
        uptime = 0
        if self.bot_start_time:
            uptime = int(time.time() - self.bot_start_time)
        
        health_data = {
            "status": "healthy",
            "service": "bxh-music-bot",
            "uptime_seconds": uptime,
            "timestamp": int(time.time())
        }
        
        self._set_headers(content_type="application/json")
        self.wfile.write(json.dumps(health_data).encode())
    
    def _handle_ping(self):
        """Handle /ping endpoint - simple text response."""
        self._set_headers()
        self.wfile.write(b"pong")
    
    def _handle_status(self) -> None:
        """Handle /status endpoint - detailed bot information."""
        uptime = 0
        uptime_str = "Unknown"
        
        if self.bot_start_time:
            uptime = int(time.time() - self.bot_start_time)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            seconds = uptime % 60
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        
        status_data = {
            "status": "online",
            "bot": "bxh-music-bot",
            "uptime": uptime_str,
            "uptime_seconds": uptime,
            "message": "Bot is alive! ♪(｡◕‿◕｡)",
            "timestamp": int(time.time())
        }
        
        self._set_headers(content_type="application/json")
        self.wfile.write(json.dumps(status_data, indent=2).encode())
    
    def _handle_not_found(self):
        """Handle unknown endpoints."""
        self._set_headers(status=404)
        self.wfile.write(b"Not Found - Try /health, /ping, or /status")


def _self_ping_task(ping_url):
    """
    Background task that periodically pings the configured URL.
    Runs in a separate daemon thread with random intervals between 5-15 minutes.
    
    Args:
        ping_url: The URL to ping (from PING_URL environment variable)
    """
    if not requests:
        logger.warning("requests library not available, self-ping disabled")
        return
    
    logger.info(f"Self-ping task started, will ping: {ping_url}")
    
    while True:
        try:
            # Random interval between 5 and 15 minutes
            interval_minutes = random.randint(5, 15)
            interval_seconds = interval_minutes * 60
            
            logger.info(f"Next self-ping in {interval_minutes} minutes")
            time.sleep(interval_seconds)
            
            # Make the ping request
            response = requests.get(ping_url, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Self-ping successful: {ping_url} (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Self-ping failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in self-ping task: {e}")


def run_health_server(port=None, bot_start_time=None):
    """
    Start the health check HTTP server in a separate daemon thread.
    Also starts the self-ping task if PING_URL is configured.
    
    Args:
        port: Port to run the server on (default: 8080, or PORT env var)
        bot_start_time: Timestamp when the bot started (for uptime calculation)
    """
    # Get port from environment variable or use default
    if port is None:
        port = int(os.getenv("PORT", 8080))
    
    # Set bot start time for the handler
    HealthCheckHandler.bot_start_time = bot_start_time
    
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health check server starting on port {port}")
        logger.info(f"Available endpoints: /health, /ping, /status")
        
        # Run server in a daemon thread so it doesn't block bot startup
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        logger.info(f"Health check server running at http://0.0.0.0:{port}")
        
        # Start self-ping task if PING_URL is configured
        ping_url = os.getenv("PING_URL")
        if ping_url:
            logger.info(f"PING_URL configured, starting self-ping task")
            ping_thread = Thread(target=_self_ping_task, args=(ping_url,), daemon=True)
            ping_thread.start()
        else:
            logger.info("PING_URL not configured, self-ping disabled")
        
        return server
        
    except OSError as e:
        if e.errno == 48 or "Address already in use" in str(e):
            logger.error(f"Port {port} is already in use. Health server not started.")
        else:
            logger.error(f"Failed to start health server: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error starting health server: {e}")
        return None


if __name__ == "__main__":
    # For testing the health server standalone
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    print("Starting health check server for testing...")
    print("Press Ctrl+C to stop")
    
    server = run_health_server(bot_start_time=time.time())
    
    if server:
        try:
            # Keep the main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down health server...")
            server.shutdown()

# Made with Bob
