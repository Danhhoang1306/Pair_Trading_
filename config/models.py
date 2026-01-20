"""
Unified Configuration Models
All configuration dataclasses in one place
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from pathlib import Path


@dataclass
class MT5Config:
    """MetaTrader 5 connection configuration"""
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    path: Optional[str] = None
    timeout: int = 60000

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolSpec:
    """Symbol specification (loaded from MT5)"""
    symbol: str
    contract_size: float
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    tick_size: float = 0.01
    point_value: float = 1.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradingParameters:
    """Trading signal and execution parameters"""
    # Entry/Exit thresholds
    entry_threshold: float = 2.0
    exit_threshold: float = 0.5
    stop_loss_zscore: float = 3.5

    # Position limits
    max_positions: int = 10
    volume_multiplier: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelParameters:
    """Statistical model parameters"""
    # Rolling window
    rolling_window_size: int = 1000
    update_interval: int = 60  # seconds

    # Hedge ratio
    hedge_drift_threshold: float = 0.05

    # Cointegration (advanced)
    cointegration_lookback: int = 252
    adf_significance: float = 0.05
    min_half_life: int = 5
    max_half_life: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskParameters:
    """Risk management parameters - 3 layers"""
    # Layer 1: Per-Setup Risk
    max_loss_per_setup_pct: float = 2.0
    max_loss_per_setup_amount: Optional[float] = None

    # Layer 2: Total Portfolio Risk
    max_total_unrealized_loss_pct: float = 5.0
    max_total_unrealized_loss_amount: Optional[float] = None

    # Layer 3: Daily Risk
    daily_loss_limit_pct: float = 10.0
    daily_loss_limit_amount: Optional[float] = None

    # Other limits
    max_position_pct: float = 20.0
    max_drawdown_pct: float = 20.0
    max_daily_trades: int = 50
    max_consecutive_losses: int = 5

    # Session times (for daily reset)
    session_start_time: str = "00:00"
    session_end_time: str = "23:59"

    def get_per_setup_limit(self, balance: float) -> float:
        """Calculate per-setup loss limit in dollars"""
        if self.max_loss_per_setup_amount:
            return self.max_loss_per_setup_amount
        return balance * (self.max_loss_per_setup_pct / 100.0)

    def get_total_portfolio_limit(self, balance: float) -> float:
        """Calculate total portfolio loss limit in dollars"""
        if self.max_total_unrealized_loss_amount:
            return self.max_total_unrealized_loss_amount
        return balance * (self.max_total_unrealized_loss_pct / 100.0)

    def get_daily_limit(self, balance: float) -> float:
        """Calculate daily loss limit in dollars"""
        if self.daily_loss_limit_amount:
            return self.daily_loss_limit_amount
        return balance * (self.daily_loss_limit_pct / 100.0)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RebalancerParameters:
    """Pyramiding and rebalancing parameters"""
    # Pyramiding
    scale_interval: float = 0.5  # Z-score interval for scaling
    initial_fraction: float = 0.33  # First entry uses 33% of position

    # Volume rebalancing
    min_adjustment_interval: int = 3600  # Min seconds between adjustments
    volume_imbalance_threshold: float = 0.10  # 10% imbalance trigger

    # Entry cooldown
    entry_min_time_between: int = 60  # Min seconds between entries

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FeatureFlags:
    """Enable/disable features"""
    enable_pyramiding: bool = True
    enable_volume_rebalancing: bool = True
    enable_regime_filter: bool = False
    enable_entry_cooldown: bool = True
    enable_manual_position_sync: bool = True
    enable_state_persistence: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemParameters:
    """System-level parameters"""
    magic_number: int = 234000
    zscore_history_size: int = 200
    position_data_dir: str = "positions"
    log_level: str = "INFO"
    timezone: str = "UTC"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TransactionCosts:
    """Transaction cost parameters"""
    commission_per_lot: float = 2.50  # USD
    spread_bps: float = 2.0  # Basis points
    slippage_bps: float = 2.0  # Basis points

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PairConfig:
    """
    Complete configuration for a trading pair

    This is the MASTER config - contains ALL settings for a pair.
    No more fragmentation!
    """
    # Identification
    name: str
    primary_symbol: str
    secondary_symbol: str

    # Parameters (all contained in sub-configs)
    trading: TradingParameters = field(default_factory=TradingParameters)
    model: ModelParameters = field(default_factory=ModelParameters)
    risk: RiskParameters = field(default_factory=RiskParameters)
    rebalancer: RebalancerParameters = field(default_factory=RebalancerParameters)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    system: SystemParameters = field(default_factory=SystemParameters)
    costs: TransactionCosts = field(default_factory=TransactionCosts)

    # Metadata
    description: str = ""
    risk_level: str = "MEDIUM"  # LOW, MEDIUM, HIGH

    def to_dict(self) -> Dict[str, Any]:
        """Convert to nested dictionary"""
        return {
            'name': self.name,
            'primary_symbol': self.primary_symbol,
            'secondary_symbol': self.secondary_symbol,
            'description': self.description,
            'risk_level': self.risk_level,
            'trading': self.trading.to_dict(),
            'model': self.model.to_dict(),
            'risk': self.risk.to_dict(),
            'rebalancer': self.rebalancer.to_dict(),
            'features': self.features.to_dict(),
            'system': self.system.to_dict(),
            'costs': self.costs.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PairConfig':
        """Create from nested dictionary"""
        return cls(
            name=data['name'],
            primary_symbol=data['primary_symbol'],
            secondary_symbol=data['secondary_symbol'],
            description=data.get('description', ''),
            risk_level=data.get('risk_level', 'MEDIUM'),
            trading=TradingParameters(**data.get('trading', {})),
            model=ModelParameters(**data.get('model', {})),
            risk=RiskParameters(**data.get('risk', {})),
            rebalancer=RebalancerParameters(**data.get('rebalancer', {})),
            features=FeatureFlags(**data.get('features', {})),
            system=SystemParameters(**data.get('system', {})),
            costs=TransactionCosts(**data.get('costs', {})),
        )

    def get_flat_dict(self) -> Dict[str, Any]:
        """
        Get flattened dictionary for backward compatibility
        Used by legacy code that expects flat config
        """
        flat = {
            'name': self.name,
            'primary_symbol': self.primary_symbol,
            'secondary_symbol': self.secondary_symbol,
        }

        # Flatten all sub-configs
        flat.update(self.trading.to_dict())
        flat.update(self.model.to_dict())
        flat.update(self.risk.to_dict())
        flat.update(self.rebalancer.to_dict())
        flat.update(self.features.to_dict())
        flat.update(self.system.to_dict())
        flat.update(self.costs.to_dict())

        return flat


@dataclass
class GlobalConfig:
    """Global system configuration"""
    # MT5 connection
    mt5: MT5Config = field(default_factory=MT5Config)

    # Active pairs
    pairs: Dict[str, PairConfig] = field(default_factory=dict)

    # Symbol cache (loaded from MT5)
    symbols: Dict[str, SymbolSpec] = field(default_factory=dict)

    # Global defaults (applied to all pairs if not overridden)
    default_risk: RiskParameters = field(default_factory=RiskParameters)
    default_features: FeatureFlags = field(default_factory=FeatureFlags)
    default_system: SystemParameters = field(default_factory=SystemParameters)

    # Metadata
    version: str = "2.0.0"
    config_format: str = "unified_v1"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML export"""
        return {
            'version': self.version,
            'config_format': self.config_format,
            'mt5': self.mt5.to_dict(),
            'global_defaults': {
                'risk': self.default_risk.to_dict(),
                'features': self.default_features.to_dict(),
                'system': self.default_system.to_dict(),
            },
            'pairs': {
                name: pair.to_dict()
                for name, pair in self.pairs.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GlobalConfig':
        """Create from dictionary loaded from YAML"""
        # Parse MT5 config
        mt5_config = MT5Config(**data.get('mt5', {}))

        # Parse global defaults
        global_defaults = data.get('global_defaults', {})
        default_risk = RiskParameters(**global_defaults.get('risk', {}))
        default_features = FeatureFlags(**global_defaults.get('features', {}))
        default_system = SystemParameters(**global_defaults.get('system', {}))

        # Parse pairs
        pairs = {}
        for name, pair_data in data.get('pairs', {}).items():
            pairs[name] = PairConfig.from_dict(pair_data)

        return cls(
            version=data.get('version', '2.0.0'),
            config_format=data.get('config_format', 'unified_v1'),
            mt5=mt5_config,
            pairs=pairs,
            default_risk=default_risk,
            default_features=default_features,
            default_system=default_system,
        )
