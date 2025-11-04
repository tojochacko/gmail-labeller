"""Test script to verify logging is working."""

import asyncio
from uuid import uuid4
from backend.app.main import create_app
from backend.app.services.gmail_toolkit import GmailService
import logging

# Create app (this will configure logging)
app = create_app()

# Get a logger
logger = logging.getLogger(__name__)

# Test logging at different levels
logger.debug("🔍 This is a DEBUG message")
logger.info("ℹ️  This is an INFO message")
logger.warning("⚠️  This is a WARNING message")
logger.error("❌ This is an ERROR message")

print("\n✅ Logging is configured and working!")
print("You should see the log messages above with timestamps and log levels.")
