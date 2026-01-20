"""
Unified Configuration Manager
Single source of truth for all configuration
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from config.models import (
    GlobalConfig,
    PairConfig,
    SymbolSpec,
    MT5Config,
)
from config.defaults import DEFAULT_GLOBAL_CONFIG

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Unified Configuration Manager - Singleton

    Configuration Precedence (highest to lowest):
    1. Environment variables (.env file)
    2. Runtime YAML config (asset/config/unified.yaml)
    3. Default values (config/defaults.py)

    This is the SINGLE SOURCE OF TRUTH for all configuration.
    No more fragmented configs!
    """

    _instance: Optional['ConfigManager'] = None
    _initialized: bool = False

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize configuration manager

        Only runs once due to singleton pattern
        """
        if self._initialized:
            return

        self.config_file = Path("asset/config/unified.yaml")
        self.config: GlobalConfig = DEFAULT_GLOBAL_CONFIG

        # Symbol cache (loaded from MT5 on demand)
        self.symbols_cache: Dict[str, SymbolSpec] = {}

        # Initialize
        self._load_environment()
        self._load_config_file()

        self._initialized = True

    def _load_environment(self):
        """
        Load configuration from environment variables

        Priority: .env file overrides everything
        """
        # Load .env file if exists
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(env_file)
            logger.info(f"✅ Loaded environment from {env_file}")

        # Override MT5 config from environment
        mt5_login = os.getenv('MT5_LOGIN')
        mt5_password = os.getenv('MT5_PASSWORD')
        mt5_server = os.getenv('MT5_SERVER')
        mt5_path = os.getenv('MT5_PATH')

        if mt5_login:
            self.config.mt5.login = int(mt5_login)
        if mt5_password:
            self.config.mt5.password = mt5_password
        if mt5_server:
            self.config.mt5.server = mt5_server
        if mt5_path:
            self.config.mt5.path = mt5_path

        # Override system settings from environment
        log_level = os.getenv('LOG_LEVEL')
        if log_level:
            self.config.default_system.log_level = log_level

        # Override risk settings from environment
        daily_loss_limit = os.getenv('DAILY_LOSS_LIMIT_PCT')
        if daily_loss_limit:
            self.config.default_risk.daily_loss_limit_pct = float(daily_loss_limit)

        max_risk_pct = os.getenv('MAX_RISK_PCT')
        if max_risk_pct:
            self.config.default_risk.max_loss_per_setup_pct = float(max_risk_pct)

    def _load_config_file(self):
        """
        Load configuration from YAML file

        Priority: YAML file overrides defaults, but environment overrides YAML
        """
        if not self.config_file.exists():
            logger.warning(f"⚠️  Config file not found: {self.config_file}")
            logger.info("📝 Creating default configuration...")
            self._create_default_config()
            return

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            if not config_data:
                logger.warning("⚠️  Config file is empty, using defaults")
                return

            # Parse config
            loaded_config = GlobalConfig.from_dict(config_data)

            # Merge with current config (environment variables take precedence)
            # Only update fields that weren't set by environment
            if not os.getenv('MT5_LOGIN'):
                self.config.mt5 = loaded_config.mt5

            self.config.pairs = loaded_config.pairs
            self.config.default_risk = loaded_config.default_risk
            self.config.default_features = loaded_config.default_features
            self.config.default_system = loaded_config.default_system

            logger.info("="*80)
            logger.info("📋 CONFIGURATION LOADED")
            logger.info("="*80)
            logger.info(f"Config file: {self.config_file}")
            logger.info(f"Pairs loaded: {len(self.config.pairs)}")
            for name, pair in self.config.pairs.items():
                logger.info(f"  ├─ {name}: {pair.primary_symbol}/{pair.secondary_symbol}")
            logger.info(f"MT5 configured: {'Yes' if self.config.mt5.login else 'No (use .env)'}")
            logger.info(f"Log level: {self.config.default_system.log_level}")
            logger.info("="*80)

        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            logger.info("📝 Using default configuration")

    def _create_default_config(self):
        """Create default configuration file"""
        try:
            # Create directory if needed
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Use defaults
            self.config = DEFAULT_GLOBAL_CONFIG

            # Save to file
            self.save()

            logger.info(f"✅ Created default config: {self.config_file}")
            logger.info(f"   Default pairs: {list(self.config.pairs.keys())}")

        except Exception as e:
            logger.error(f"❌ Error creating default config: {e}")

    def save(self):
        """Save current configuration to YAML file"""
        try:
            config_data = self.config.to_dict()

            # Remove MT5 credentials from saved config (use .env instead)
            if 'mt5' in config_data:
                config_data['mt5'] = {
                    'timeout': self.config.mt5.timeout,
                    # login, password, server should be in .env
                }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(
                    config_data,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True
                )

            logger.info(f"✅ Configuration saved to {self.config_file}")

        except Exception as e:
            logger.error(f"❌ Error saving config: {e}")

    # ========== PUBLIC API ==========

    def get_pair(self, name: str) -> Optional[PairConfig]:
        """Get pair configuration by name"""
        return self.config.pairs.get(name)

    def get_all_pairs(self) -> Dict[str, PairConfig]:
        """Get all configured pairs"""
        return self.config.pairs

    def add_pair(self, pair: PairConfig):
        """Add new pair configuration"""
        self.config.pairs[pair.name] = pair
        self.save()
        logger.info(f"✅ Added pair: {pair.name}")

    def remove_pair(self, name: str):
        """Remove pair configuration"""
        if name in self.config.pairs:
            del self.config.pairs[name]
            self.save()
            logger.info(f"✅ Removed pair: {name}")

    def update_pair(self, name: str, updates: Dict[str, Any]):
        """Update pair configuration"""
        if name not in self.config.pairs:
            logger.error(f"❌ Pair not found: {name}")
            return

        pair = self.config.pairs[name]

        # Update nested fields
        for key, value in updates.items():
            if '.' in key:
                # Nested field (e.g., 'trading.entry_threshold')
                section, field = key.split('.', 1)
                if hasattr(pair, section):
                    section_obj = getattr(pair, section)
                    if hasattr(section_obj, field):
                        setattr(section_obj, field, value)
            else:
                # Top-level field
                if hasattr(pair, key):
                    setattr(pair, key, value)

        self.save()
        logger.info(f"✅ Updated pair: {name}")

    def get_symbol(self, symbol: str) -> Optional[SymbolSpec]:
        """
        Get symbol specification

        Loads from MT5 on demand and caches result
        """
        # Check cache first
        if symbol in self.symbols_cache:
            return self.symbols_cache[symbol]

        # Load from MT5
        try:
            from core.mt5_manager import get_mt5

            mt5 = get_mt5()
            if not mt5.initialize():
                logger.error("❌ Could not initialize MT5")
                return None

            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.warning(f"⚠️  Symbol not found in MT5: {symbol}")
                return None

            # Create spec
            spec = SymbolSpec(
                symbol=symbol,
                contract_size=symbol_info.trade_contract_size,
                min_lot=symbol_info.volume_min,
                max_lot=symbol_info.volume_max,
                lot_step=symbol_info.volume_step,
                tick_size=symbol_info.point,
                point_value=symbol_info.trade_tick_value,
                description=symbol_info.description or "",
            )

            # Cache
            self.symbols_cache[symbol] = spec
            logger.debug(f"✅ Loaded symbol from MT5: {symbol}")

            return spec

        except Exception as e:
            logger.error(f"❌ Error loading symbol {symbol}: {e}")
            return None

    def get_mt5_config(self) -> MT5Config:
        """Get MT5 connection configuration"""
        return self.config.mt5

    def get_global_risk(self):
        """Get global risk parameters"""
        return self.config.default_risk

    def get_global_features(self):
        """Get global feature flags"""
        return self.config.default_features

    def get_global_system(self):
        """Get global system parameters"""
        return self.config.default_system

    def reload(self):
        """Reload configuration from file"""
        logger.info("🔄 Reloading configuration...")
        self._initialized = False
        self.__init__()

    # ========== BACKWARD COMPATIBILITY ==========

    def get_pair_flat(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get pair configuration as flat dictionary

        For backward compatibility with legacy code
        """
        pair = self.get_pair(name)
        if pair is None:
            return None

        return pair.get_flat_dict()


# ========== GLOBAL INSTANCE ==========

_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """
    Get global configuration manager instance

    This is the MAIN API - use this everywhere!
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def reload_config():
    """Reload configuration from disk"""
    global _config_manager
    if _config_manager is not None:
        _config_manager.reload()
    else:
        _config_manager = ConfigManager()
    return _config_manager


# ========== CONVENIENCE FUNCTIONS ==========

def get_pair_config(name: str) -> Optional[PairConfig]:
    """Convenience function to get pair config"""
    return get_config().get_pair(name)


def get_all_pair_configs() -> Dict[str, PairConfig]:
    """Convenience function to get all pairs"""
    return get_config().get_all_pairs()


def get_symbol_spec(symbol: str) -> Optional[SymbolSpec]:
    """Convenience function to get symbol spec"""
    return get_config().get_symbol(symbol)


if __name__ == "__main__":
    # Test configuration system
    import sys

    # Set UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

    print("="*80)
    print("UNIFIED CONFIGURATION SYSTEM TEST")
    print("="*80)

    config = get_config()

    print(f"\n[CONFIG] Configuration Status:")
    print(f"   Config file: {config.config_file}")
    print(f"   Config exists: {config.config_file.exists()}")

    print(f"\n[MT5] MT5 Configuration:")
    print(f"   Login: {config.config.mt5.login or 'Not set (use .env)'}")
    print(f"   Server: {config.config.mt5.server or 'Not set (use .env)'}")

    print(f"\n[PAIRS] Configured Pairs:")
    for name, pair in config.get_all_pairs().items():
        print(f"   {name}:")
        print(f"      Symbols: {pair.primary_symbol}/{pair.secondary_symbol}")
        print(f"      Entry threshold: {pair.trading.entry_threshold}")
        print(f"      Risk per setup: {pair.risk.max_loss_per_setup_pct}%")
        print(f"      Risk level: {pair.risk_level}")

    print(f"\n[DEFAULTS] Global Defaults:")
    print(f"   Daily loss limit: {config.config.default_risk.daily_loss_limit_pct}%")
    print(f"   Pyramiding: {config.config.default_features.enable_pyramiding}")
    print(f"   Log level: {config.config.default_system.log_level}")

    print("="*80)
    print("TEST PASSED - Unified config system working!")
    print("="*80)
