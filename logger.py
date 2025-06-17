import sys
import time
from pathlib import Path
from loguru import logger

# Configure logger with better structure and rotation
logger.remove(0)
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>[{time:YYYY-MM-DD HH:mm:ss}]</green> <cyan>[{level}]</cyan>: <yellow>{message}</yellow>",
    colorize=True,
    backtrace=True,
    diagnose=True
)
logger.add(
    f"logs/{int(time.time())}.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} [{level}]: {message}",
    colorize=True,
    rotation="10 MB",
    retention="30 days"
)

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)