"""
Signal Handlers
"""
import logging
import signal as sig

logger = logging.getLogger(__name__)


class SignalHandlers:
    """Handles system signals"""
    
    def __init__(self, system):
        self.system = system
    
    def signal_handler(self, signum, frame):
        """Handle CTRL+C and other signals"""
        logger.info(f"\nReceived signal {signum} - shutting down gracefully...")
        self.system.stop()
