"""
MT5 Connection Manager - Singleton Pattern
Ensures only ONE MT5 connection for the entire system

CRITICAL: MT5 should only be initialized ONCE per application.
Multiple initialize() calls can cause connection errors.

Usage:
    # In main_cli.py (startup):
    mt5_mgr = MT5Manager()
    if not mt5_mgr.initialize():
        sys.exit(1)

    # In any other module:
    from core.mt5_manager import get_mt5_manager
    mt5 = get_mt5_manager().mt5
    positions = mt5.positions_get()
"""

import MetaTrader5 as mt5
import logging
from typing import Optional
from threading import Lock

logger = logging.getLogger(__name__)


class MT5Manager:
    """
    Singleton MT5 Connection Manager

    Ensures only ONE MT5 connection across the entire application.
    Thread-safe with automatic reconnection support.

    Design:
    - Singleton pattern: Only one instance ever created
    - Thread-safe: Lock protects initialization
    - Lazy initialization: Initialize on first use
    - Auto-reconnect: Detects disconnection and reconnects
    """

    _instance: Optional['MT5Manager'] = None
    _lock = Lock()
    _initialized = False
    _account_info = None

    def __new__(cls):
        """Singleton pattern: always return same instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, login=None, password=None, server=None, path=None, timeout=60000) -> bool:
        """
        Initialize MT5 connection (thread-safe, only once)

        This should be called ONCE at application startup (main_cli.py).
        Subsequent calls will return True if already initialized.

        Args:
            login: MT5 account login (optional, uses config if not provided)
            password: MT5 password (optional, uses config if not provided)
            server: MT5 server (optional, uses config if not provided)
            path: MT5 terminal path (optional)
            timeout: Connection timeout in milliseconds

        Returns:
            bool: True if initialized successfully (or already initialized)
        """
        with self._lock:
            # If already initialized, check connection status
            if self._initialized:
                if self.is_connected():
                    logger.debug("[MT5-MANAGER] Already initialized and connected")
                    return True
                else:
                    logger.warning("[MT5-MANAGER] Was initialized but disconnected - reconnecting...")
                    self._initialized = False

            # Get credentials from config if not provided
            from config import MT5_CONFIG

            _login = login or MT5_CONFIG.get('login')
            _password = password or MT5_CONFIG.get('password')
            _server = server or MT5_CONFIG.get('server')
            _path = path or MT5_CONFIG.get('path', '')
            _timeout = timeout or MT5_CONFIG.get('timeout', 60000)

            try:
                logger.info("[MT5-MANAGER] Initializing connection...")

                # TRY METHOD 1: Initialize without credentials (if MT5 already logged in)
                if not _login or not _password or not _server or _login == 0:
                    logger.info("[MT5-MANAGER] No credentials provided, trying simple initialization...")
                    logger.info("[MT5-MANAGER] Assuming MT5 terminal is already logged in")

                    if _path:
                        success = mt5.initialize(path=_path, timeout=_timeout)
                    else:
                        success = mt5.initialize(timeout=_timeout)

                    if not success:
                        error = mt5.last_error()
                        logger.error(f"[MT5-MANAGER] ❌ Simple initialization failed: {error}")
                        logger.error("[MT5-MANAGER] Please ensure MT5 terminal is running and logged in")
                        return False

                else:
                    # METHOD 2: Initialize with credentials
                    logger.info("[MT5-MANAGER] Initializing with credentials...")

                    if _path:
                        success = mt5.initialize(
                            path=_path,
                            login=_login,
                            password=_password,
                            server=_server,
                            timeout=_timeout
                        )
                    else:
                        success = mt5.initialize(
                            login=_login,
                            password=_password,
                            server=_server,
                            timeout=_timeout
                        )

                    if not success:
                        error = mt5.last_error()
                        logger.warning(f"[MT5-MANAGER] ⚠️ Credential-based initialization failed: {error}")
                        logger.info("[MT5-MANAGER] Trying simple initialization (assuming terminal is logged in)...")

                        # Fallback to simple initialization
                        if _path:
                            success = mt5.initialize(path=_path, timeout=_timeout)
                        else:
                            success = mt5.initialize(timeout=_timeout)

                        if not success:
                            error2 = mt5.last_error()
                            logger.error(f"[MT5-MANAGER] ❌ All initialization methods failed")
                            logger.error(f"[MT5-MANAGER] Error 1 (with credentials): {error}")
                            logger.error(f"[MT5-MANAGER] Error 2 (simple): {error2}")
                            return False

                # Verify connection by getting account info
                self._account_info = mt5.account_info()
                if self._account_info is None:
                    logger.error("[MT5-MANAGER] ❌ Initialized but cannot get account info")
                    mt5.shutdown()
                    return False

                # Get terminal info
                terminal_info = mt5.terminal_info()

                self._initialized = True

                logger.info("=" * 80)
                logger.info("[MT5-MANAGER] ✅ CONNECTION ESTABLISHED")
                logger.info("=" * 80)
                logger.info(f"  Account:     {self._account_info.login}")
                logger.info(f"  Server:      {self._account_info.server}")
                logger.info(f"  Balance:     ${self._account_info.balance:,.2f}")
                logger.info(f"  Equity:      ${self._account_info.equity:,.2f}")
                logger.info(f"  Leverage:    1:{self._account_info.leverage}")
                logger.info(f"  Currency:    {self._account_info.currency}")
                if terminal_info:
                    logger.info(f"  Terminal:    {terminal_info.name} (Build {terminal_info.build})")
                logger.info("=" * 80)

                return True

            except Exception as e:
                logger.error(f"[MT5-MANAGER] ❌ Exception during initialization: {e}")
                import traceback
                traceback.print_exc()
                return False

    def is_connected(self) -> bool:
        """
        Check if MT5 is connected and responsive

        Returns:
            bool: True if connected
        """
        if not self._initialized:
            return False

        try:
            # Try to get account info (lightweight check)
            info = mt5.account_info()
            return info is not None
        except:
            return False

    def ensure_connected(self) -> bool:
        """
        Ensure MT5 is connected (with auto-reconnect)

        Call this before any MT5 operation if you want auto-reconnect.
        However, in production, you should handle disconnection explicitly.

        Returns:
            bool: True if MT5 is ready to use
        """
        if self._initialized and self.is_connected():
            return True

        if self._initialized and not self.is_connected():
            logger.error("[MT5-MANAGER] ⚠️ Connection lost - manual reconnection required")
            return False

        # Not initialized yet - try to initialize
        logger.warning("[MT5-MANAGER] Not initialized - attempting initialization...")
        return self.initialize()

    def get_account_info(self):
        """
        Get cached account info (or fetch fresh)

        Returns:
            AccountInfo object or None
        """
        if not self._initialized:
            logger.error("[MT5-MANAGER] Not initialized")
            return None

        try:
            # Get fresh account info
            info = mt5.account_info()
            if info:
                self._account_info = info
            return info
        except Exception as e:
            logger.error(f"[MT5-MANAGER] Error getting account info: {e}")
            return self._account_info  # Return cached

    def shutdown(self):
        """
        Shutdown MT5 connection

        This should only be called at application exit.
        """
        with self._lock:
            if self._initialized:
                try:
                    mt5.shutdown()
                    self._initialized = False
                    self._account_info = None
                    logger.info("[MT5-MANAGER] ✅ Connection closed")
                except Exception as e:
                    logger.error(f"[MT5-MANAGER] Error during shutdown: {e}")

    @property
    def mt5(self):
        """
        Get MT5 module (use this for all MT5 operations)

        Returns:
            MetaTrader5 module

        Raises:
            RuntimeError: If not initialized

        Usage:
            mt5_mgr = get_mt5_manager()
            positions = mt5_mgr.mt5.positions_get()
            tick = mt5_mgr.mt5.symbol_info_tick('BTCUSD')
        """
        if not self._initialized:
            raise RuntimeError(
                "[MT5-MANAGER] Not initialized! "
                "Call mt5_manager.initialize() in main_cli.py first."
            )

        if not self.is_connected():
            raise RuntimeError(
                "[MT5-MANAGER] Not connected! "
                "Connection was lost. Check MT5 terminal."
            )

        return mt5

    @property
    def is_initialized(self) -> bool:
        """Check if MT5 has been initialized"""
        return self._initialized

    def __repr__(self):
        """String representation"""
        if not self._initialized:
            return "MT5Manager(status=Not Initialized)"

        status = "Connected" if self.is_connected() else "Disconnected"
        account = self._account_info.login if self._account_info else "Unknown"
        return f"MT5Manager(status={status}, account={account})"

    def __enter__(self):
        """Context manager entry"""
        if not self._initialized:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        # Don't shutdown on context exit - connection should persist
        # Only shutdown explicitly at application exit
        pass


# ============================================================
# Global Singleton Instance
# ============================================================

_mt5_manager_instance = MT5Manager()


def get_mt5_manager() -> MT5Manager:
    """
    Get the global MT5Manager singleton instance

    Returns:
        MT5Manager: The singleton instance

    Usage:
        from core.mt5_manager import get_mt5_manager

        mt5_mgr = get_mt5_manager()
        mt5 = mt5_mgr.mt5

        # Now use mt5 as normal
        positions = mt5.positions_get()
        tick = mt5.symbol_info_tick('BTCUSD')
    """
    return _mt5_manager_instance


# ============================================================
# Convenience Functions
# ============================================================

def get_mt5():
    """
    Get MT5 module directly (shortcut)

    Returns:
        MetaTrader5 module

    Raises:
        RuntimeError: If not initialized

    Usage:
        from core.mt5_manager import get_mt5

        mt5 = get_mt5()
        positions = mt5.positions_get()
    """
    return get_mt5_manager().mt5


def is_mt5_connected() -> bool:
    """
    Check if MT5 is connected (shortcut)

    Returns:
        bool: True if connected
    """
    return get_mt5_manager().is_connected()
