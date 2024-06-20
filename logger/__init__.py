import sys
from pathlib import Path

from loguru import logger

fmt = '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>'

logger.remove()

logger.add(
    sink=sys.stderr,
    format=fmt,
    colorize=True
)

logger.add(
    Path(__file__).parents[1] / 'logs' / 'layer_zero_claimer.log',
    rotation='1 day',
    format=fmt
)
