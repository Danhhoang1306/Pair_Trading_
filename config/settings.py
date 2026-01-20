"""
⚠️ DEPRECATED - Use config.manager instead!

This file is kept for backward compatibility only.

MIGRATION GUIDE:
- OLD: from config.settings import get_config
- NEW: from config.manager import get_config

The new unified config system:
- Single YAML file (asset/config/unified.yaml)
- No fragmentation
- Clear precedence: .env > YAML > defaults
- Better type safety with dataclasses

See: config/manager.py, config/models.py, config/defaults.py
"""

# Legacy support - redirect to new system
import warnings
warnings.warn(
    "config.settings is deprecated. Use config.manager instead.",
    DeprecationWarning,
    stacklevel=2
)

"""
OLD Centralized Configuration System
Compatible with existing trading logic, extensible for future
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """
    Risk configuration with clear parameter names and backward compatibility

    Three types of risk limits:
    1. Per-Setup Risk: Max loss allowed for EACH individual setup
    2. Total Portfolio Risk: Max total unrealized loss across ALL positions
    3. Daily Risk: Max total loss per day (realized + unrealized)
    """

    # ========== PER-SETUP LIMITS ==========
    max_loss_per_setup_pct: float = 2.0
    max_loss_per_setup_amount: Optional[float] = None

    # ========== TOTAL PORTFOLIO LIMITS ==========
    max_total_unrealized_loss_pct: float = 5.0
    max_total_unrealized_loss_amount: Optional[float] = None

    # ========== DAILY LIMITS ==========
    daily_loss_limit_pct: float = 10.0
    daily_loss_limit_amount: Optional[float] = None

    # ========== OTHER LIMITS ==========
    max_position_pct: float = 20.0
    max_drawdown_pct: float = 20.0

    # Session times
    session_start_time: str = '00:00'
    session_end_time: str = '23:59'

    @classmethod
    def from_dict(cls, config_dict: Dict) -> 'RiskConfig':
        """
        Create RiskConfig from dict with backward compatibility

        Handles old parameter names:
        - max_risk_pct → max_loss_per_setup_pct

        Args:
            config_dict: Config dictionary (from YAML or GUI)

        Returns:
            RiskConfig instance
        """
        # ========== PER-SETUP LIMITS ==========
        # Try new parameter first, fallback to old
        max_loss_per_setup_pct = config_dict.get(
            'max_loss_per_setup_pct',
            config_dict.get('max_risk_pct', 2.0)  # Backward compatibility
        )

        max_loss_per_setup_amount = config_dict.get('max_loss_per_setup_amount')

        # ========== TOTAL PORTFOLIO LIMITS ==========
        # Default to 2.5x per-setup limit if not specified
        max_total_unrealized_loss_pct = config_dict.get(
            'max_total_unrealized_loss_pct',
            max_loss_per_setup_pct * 2.5
        )

        max_total_unrealized_loss_amount = config_dict.get('max_total_unrealized_loss_amount')

        # ========== DAILY LIMITS ==========
        daily_loss_limit_pct = config_dict.get('daily_loss_limit_pct', 10.0)
        daily_loss_limit_amount = config_dict.get('daily_loss_limit_amount')

        # ========== OTHER LIMITS ==========
        max_position_pct = config_dict.get('max_position_pct', 20.0)
        max_drawdown_pct = config_dict.get('max_drawdown_pct', 20.0)

        # Session times
        session_start_time = config_dict.get('session_start_time', '00:00')
        session_end_time = config_dict.get('session_end_time', '23:59')

        # Log migration if old parameter was used
        if 'max_risk_pct' in config_dict and 'max_loss_per_setup_pct' not in config_dict:
            logger.warning("="*80)
            logger.warning("⚠️  DEPRECATED PARAMETER DETECTED")
            logger.warning("="*80)
            logger.warning(f"Parameter 'max_risk_pct' is deprecated and ambiguous")
            logger.warning(f"Please use clear parameter names instead:")
            logger.warning(f"  - max_loss_per_setup_pct: Max loss for EACH setup")
            logger.warning(f"  - max_total_unrealized_loss_pct: Max total portfolio loss")
            logger.warning(f"")
            logger.warning(f"Auto-migration applied:")
            logger.warning(f"  max_risk_pct={config_dict['max_risk_pct']}% "
                         f"→ max_loss_per_setup_pct={max_loss_per_setup_pct}%")
            logger.warning(f"  max_total_unrealized_loss_pct auto-set to {max_total_unrealized_loss_pct}%")
            logger.warning("="*80)

        return cls(
            max_loss_per_setup_pct=max_loss_per_setup_pct,
            max_loss_per_setup_amount=max_loss_per_setup_amount,
            max_total_unrealized_loss_pct=max_total_unrealized_loss_pct,
            max_total_unrealized_loss_amount=max_total_unrealized_loss_amount,
            daily_loss_limit_pct=daily_loss_limit_pct,
            daily_loss_limit_amount=daily_loss_limit_amount,
            max_position_pct=max_position_pct,
            max_drawdown_pct=max_drawdown_pct,
            session_start_time=session_start_time,
            session_end_time=session_end_time
        )

    def get_per_setup_limit(self, balance: float) -> float:
        """
        Get per-setup loss limit in dollars

        Args:
            balance: Account balance

        Returns:
            Max loss allowed per setup in dollars
        """
        if self.max_loss_per_setup_amount:
            return self.max_loss_per_setup_amount
        return balance * (self.max_loss_per_setup_pct / 100.0)

    def get_total_portfolio_limit(self, balance: float) -> float:
        """
        Get total portfolio loss limit in dollars

        Args:
            balance: Account balance

        Returns:
            Max total unrealized loss in dollars
        """
        if self.max_total_unrealized_loss_amount:
            return self.max_total_unrealized_loss_amount
        return balance * (self.max_total_unrealized_loss_pct / 100.0)

    def get_daily_limit(self, balance: float) -> float:
        """
        Get daily loss limit in dollars

        Args:
            balance: Account balance

        Returns:
            Max daily loss in dollars
        """
        if self.daily_loss_limit_amount:
            return self.daily_loss_limit_amount
        return balance * (self.daily_loss_limit_pct / 100.0)

    def to_dict(self) -> Dict:
        """Convert to dict for GUI/logging"""
        return asdict(self)


@dataclass
class SymbolConfig:
    """Configuration for a trading symbol"""
    symbol: str
    contract_size: float
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    tick_size: float = 0.01
    point_value: float = 1.0
    
    def to_dict(self):
        return asdict(self)


@dataclass
class PairConfig:
    """
    Configuration for a trading pair
    
    COMPLETE CONFIG - Contains ALL system settings!
    No more hardcoded values anywhere!
    """
    name: str
    primary_symbol: str
    secondary_symbol: str
    
    # Symbol specs (fetched from MT5 at runtime, NOT stored in config)
    primary_contract_size: float = 1.0
    secondary_contract_size: float = 1.0
    
    # Trading parameters  
    entry_threshold: float = 2.0
    exit_threshold: float = 0.5
    stop_loss_zscore: float = 3.5
    max_positions: int = 10
    volume_multiplier: float = 1.0
    
    # Model parameters
    rolling_window_size: int = 1000
    update_interval: int = 60
    hedge_drift_threshold: float = 0.05
    
    # Risk parameters
    max_position_pct: float = 20.0
    max_risk_pct: float = 2.0
    max_drawdown_pct: float = 20.0
    daily_loss_limit: float = 5000.0
    
    # Rebalancer parameters (NEW!)
    scale_interval: float = 0.1          # Pyramiding every 0.1 z-score
    initial_fraction: float = 0.33       # First entry uses 33% of position
    min_adjustment_interval: int = 3600  # Min 1 hour between hedge adjustments
    
    # Feature flags
    enable_pyramiding: bool = True
    enable_hedge_adjustment: bool = True
    enable_regime_filter: bool = False
    
    # System parameters (NEW!)
    magic_number: int = 234000           # MT5 magic number
    zscore_history_size: int = 200       # ZScore monitor history
    position_data_dir: str = "positions" # Position persistence directory
    
    def to_dict(self):
        """
        Convert to dict for saving to config
        
        CRITICAL: Only save user-configurable settings!
        - Keep: name, symbols, all settings
        - Remove: contract_size (comes from MT5)
        """
        d = asdict(self)
        # Remove contract sizes - they're from MT5
        d.pop('primary_contract_size', None)
        d.pop('secondary_contract_size', None)
        return d


class ConfigManager:
    """
    Centralized configuration manager
    
    SIMPLIFIED DESIGN:
    - Config stores pairs with SETTINGS ONLY
    - Symbol info fetched from MT5 (not in config)
    - Clean, minimal config file
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize config manager
        
        CRITICAL: Load order is:
        1. Try to load from existing config file
        2. If file doesn't exist, create from defaults
        3. Then load the file
        
        This ensures user settings are ALWAYS loaded first!
        """
        self.config_dir = Path(__file__).parent.parent / "asset" / "config"
        self.config_file = Path(config_file) if config_file else self.config_dir / "trading_settings.yaml"
        
        # Initialize storage
        self.pairs: Dict[str, PairConfig] = {}
        self.symbols: Dict[str, SymbolConfig] = {}  # Cached from MT5
        self.global_settings: Dict[str, Any] = {}
        
        # CRITICAL: Initialize configuration in correct order
        self._initialize_config()
        
    def _initialize_config(self):
        """
        Initialize configuration with proper precedence:
        1. Load from file if exists (USER SETTINGS)
        2. Create defaults if file missing
        3. Validate loaded config
        """
        print("="*70)
        print("📋 CONFIGURATION SYSTEM INITIALIZING")
        print("="*70)
        
        # Check if config file exists
        if self.config_file.exists():
            print(f"✅ Found config file: {self.config_file}")
            print(f"   Loading user settings...")
            
            try:
                self.load_config()
                print(f"✅ Loaded {len(self.pairs)} pairs")
                print(f"   Symbols will be loaded from MT5 on demand")
                
                # Show what was loaded (settings only, no contract sizes)
                for pair_name, pair in self.pairs.items():
                    print(f"   📊 {pair_name}: {pair.primary_symbol}/{pair.secondary_symbol}")
                    print(f"      Entry: {pair.entry_threshold}, Window: {pair.rolling_window_size}")
                
            except Exception as e:
                print(f"⚠️  Error loading config: {e}")
                print(f"   Creating fresh config with defaults...")
                self.create_default_config()
                self.load_config()
        else:
            print(f"⚠️  Config file not found: {self.config_file}")
            print(f"   Creating default configuration...")
            self.create_default_config()
            self.load_config()
            print(f"✅ Created default config with {len(self.pairs)} pairs")
        
        print("="*70)
        print("")
        
    def load_config(self):
        """
        Load configuration from YAML file
        
        CRITICAL: This method loads from existing file
        It should NOT create defaults - that's done in create_default_config()
        
        Symbol specifications are NOT loaded from config!
        They are fetched from MT5 when needed.
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config:
                raise ValueError("Config file is empty")
            
            # Parse global settings (optional)
            self.global_settings = config.get('global', {})
            
            # SKIP symbols section - we get symbols from MT5!
            # This makes config simpler and always in sync with broker
            
            # Parse pairs (required)
            pairs_data = config.get('pairs', [])
            if not pairs_data:
                print("⚠️  Warning: No pairs found in config")
            
            for pair_data in pairs_data:
                try:
                    # Create pair config
                    # Contract sizes will be fetched from MT5 when needed
                    pair = PairConfig(**pair_data)
                    self.pairs[pair.name] = pair
                except Exception as e:
                    print(f"⚠️  Error loading pair {pair_data.get('name', 'unknown')}: {e}")
                    
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise Exception(f"Error loading config: {e}")
    
    def create_default_config(self):
        """
        Create default configuration file
        
        CRITICAL: We do NOT store symbol specifications here!
        Symbol info (contract_size, min_lot, etc.) is fetched from MT5 dynamically.
        This keeps config clean and always in sync with broker.
        
        We DO store ALL trading system parameters here!
        """
        default_config = {
            'global': {
                'timezone': 'UTC',
                'log_level': 'INFO'
            },
            'pairs': [
                {
                    'name': 'XAU_XAG',
                    'primary_symbol': 'BTCUSD',
                    'secondary_symbol': 'ETHUSD',
                    
                    # Trading parameters
                    'entry_threshold': 2.0,
                    'exit_threshold': 0.5,
                    'stop_loss_zscore': 3.5,
                    'max_positions': 10,
                    'volume_multiplier': 1.0,
                    
                    # Model parameters
                    'rolling_window_size': 1000,
                    'update_interval': 60,
                    'hedge_drift_threshold': 0.05,
                    
                    # Risk parameters
                    'max_position_pct': 20.0,
                    'max_risk_pct': 2.0,
                    'max_drawdown_pct': 20.0,
                    'daily_loss_limit': 5000.0,
                    
                    # Rebalancer parameters
                    'scale_interval': 0.1,
                    'initial_fraction': 0.33,
                    'min_adjustment_interval': 3600,
                    
                    # Feature flags
                    'enable_pyramiding': True,
                    'enable_hedge_adjustment': True,
                    'enable_regime_filter': False,
                    
                    # System parameters
                    'magic_number': 234000,
                    'zscore_history_size': 200,
                    'position_data_dir': 'positions'
                },
                {
                    'name': 'NAS_SP',
                    'primary_symbol': 'NAS100.r',
                    'secondary_symbol': 'SP500.r',
                    
                    'entry_threshold': 2.0,
                    'exit_threshold': 0.5,
                    'stop_loss_zscore': 3.5,
                    'max_positions': 10,
                    'volume_multiplier': 1.0,
                    'rolling_window_size': 1000,
                    'update_interval': 60,
                    'hedge_drift_threshold': 0.05,
                    'max_position_pct': 20.0,
                    'max_risk_pct': 2.0,
                    'max_drawdown_pct': 20.0,
                    'daily_loss_limit': 5000.0,
                    'scale_interval': 0.1,
                    'initial_fraction': 0.33,
                    'min_adjustment_interval': 3600,
                    'enable_pyramiding': True,
                    'enable_hedge_adjustment': True,
                    'enable_regime_filter': False,
                    'magic_number': 234000,
                    'zscore_history_size': 200,
                    'position_data_dir': 'positions'
                }
            ]
        }
        
        # Create config directory if needed
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write default config
        with open(self.config_file, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)
        
        print(f"✅ Created default configuration: {self.config_file}")
        print(f"   Symbol info will be fetched from MT5 dynamically")
        print(f"   All {len(default_config['pairs'])} pairs configured with complete settings")
    
    def get_pair(self, name: str) -> Optional[PairConfig]:
        """Get pair configuration by name"""
        return self.pairs.get(name)
    
    def get_symbol(self, symbol: str) -> Optional[SymbolConfig]:
        """
        Get symbol configuration with lazy loading

        CRITICAL: Only loads the specific symbol requested!
        This prevents crashes from non-existent symbols.
        Returns None if symbol doesn't exist in MT5.
        """
        # Check cache first
        if symbol in self.symbols:
            return self.symbols[symbol]

        # Lazy load from MT5 - only this specific symbol!
        try:
            from core.mt5_manager import get_mt5
            mt5 = get_mt5()

            # Initialize if needed
            if not mt5.initialize():
                print(f"⚠️  Could not initialize MT5 for {symbol}")
                return None

            # Try to get this specific symbol
            symbol_info = mt5.symbol_info(symbol)
            
            if symbol_info is None:
                # Symbol doesn't exist
                print(f"⚠️  Symbol '{symbol}' not found in MT5")
                return None
            
            # Symbol exists! Create config and cache it
            symbol_config = SymbolConfig(
                symbol=symbol,
                contract_size=symbol_info.trade_contract_size,
                min_lot=symbol_info.volume_min,
                max_lot=symbol_info.volume_max,
                lot_step=symbol_info.volume_step,
                tick_size=symbol_info.point,
                point_value=symbol_info.trade_tick_value
            )
            
            # Cache for future use
            self.symbols[symbol] = symbol_config
            print(f"✅ Loaded {symbol} from MT5 (contract_size={symbol_config.contract_size})")
            
            return symbol_config
            
        except Exception as e:
            print(f"⚠️  Error loading symbol {symbol}: {e}")
            return None
    
    def get_all_pairs(self) -> Dict[str, PairConfig]:
        """Get all configured pairs"""
        return self.pairs
    
    def get_all_symbols(self) -> Dict[str, SymbolConfig]:
        """
        Get all available symbols
        
        CRITICAL: This should NOT be called at startup!
        Symbols are loaded on-demand only when user enters a symbol name.
        This prevents crashes from non-existent symbols.
        """
        # Return empty dict - symbols loaded on demand via get_symbol()
        return self.symbols
    
    def add_pair(self, pair: PairConfig):
        """Add new pair configuration"""
        self.pairs[pair.name] = pair
        self.save_config()
    
    def add_symbol(self, symbol: SymbolConfig):
        """Add new symbol configuration"""
        self.symbols[symbol.symbol] = symbol
        self.save_config()
    
    def save_config(self):
        """Save current configuration to file"""
        config = {
            'global': self.global_settings,
            'symbols': [s.to_dict() for s in self.symbols.values()],
            'pairs': [p.to_dict() for p in self.pairs.values()]
        }
        
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    def update_pair_settings(self, name: str, settings: Dict[str, Any]):
        """Update pair settings from GUI"""
        if name in self.pairs:
            pair = self.pairs[name]
            for key, value in settings.items():
                if hasattr(pair, key):
                    setattr(pair, key, value)
            self.save_config()
    
    def export_to_json(self, filepath: str):
        """Export configuration to JSON (for GUI)"""
        config = {
            'global': self.global_settings,
            'symbols': {s: sym.to_dict() for s, sym in self.symbols.items()},
            'pairs': {p: pair.to_dict() for p, pair in self.pairs.items()}
        }
        
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=4)


# Global instance
_config_manager = None

def get_config() -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def reload_config():
    """Reload configuration from file"""
    global _config_manager
    _config_manager = ConfigManager()
    return _config_manager


if __name__ == "__main__":
    # Test configuration
    config = get_config()
    
    print("="*70)
    print("CONFIGURATION TEST")
    print("="*70)
    
    print(f"\nAvailable Pairs:")
    for name, pair in config.get_all_pairs().items():
        print(f"  {name}: {pair.primary_symbol}/{pair.secondary_symbol}")
        print(f"    Entry: {pair.entry_threshold}, Exit: {pair.exit_threshold}")
        print(f"    Window: {pair.rolling_window_size}, Pyramiding: {pair.enable_pyramiding}")
    
    print(f"\nAvailable Symbols:")
    for symbol, sym_config in config.get_all_symbols().items():
        print(f"  {symbol}: Contract={sym_config.contract_size}, Min={sym_config.min_lot}")
    
    print(f"\nGlobal Settings:")
    for key, value in config.global_settings.items():
        print(f"  {key}: {value}")
