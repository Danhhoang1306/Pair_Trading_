"""
Base Thread Class
"""
import threading
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseThread(ABC):
    """Base class for all trading system threads"""
    
    def __init__(self, name: str, system):
        self.name = name
        self.system = system
        self.thread = None
        self.running = False
        
    def start(self):
        """Start the thread"""
        if self.thread and self.thread.is_alive():
            logger.warning(f"{self.name} already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self.thread.start()
        logger.info(f"{self.name} started")
        
    def stop(self):
        """Stop the thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"{self.name} stopped")
        
    def _run_wrapper(self):
        """Wrapper with error handling"""
        try:
            self.run()
        except Exception as e:
            logger.error(f"{self.name} error: {e}")
            import traceback
            traceback.print_exc()
    
    @abstractmethod
    def run(self):
        """Main thread loop - override in subclasses"""
        pass
