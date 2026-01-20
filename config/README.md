# Unified Configuration System

## Quick Start

```python
from config.manager import get_config

# Get configuration
config = get_config()

# Get pair settings
pair = config.get_pair('BTC_ETH')
entry_threshold = pair.trading.entry_threshold
max_risk = pair.risk.max_loss_per_setup_pct

# Get symbol specs from MT5
symbol = config.get_symbol('BTCUSD')
contract_size = symbol.contract_size
```

## Architecture

```
config/
├── manager.py      # ConfigManager (main API) - USE THIS!
├── models.py       # Type-safe dataclasses
├── defaults.py     # Default values
├── settings.py     # DEPRECATED - backward compat only
├── trading_settings.py  # DEPRECATED
├── risk_limits.py  # DEPRECATED
└── instruments.py  # DEPRECATED
```

## Configuration File

**Single YAML file:** `asset/config/unified.yaml`

```yaml
version: '2.0.0'
config_format: unified_v1

# Global defaults
global_defaults:
  risk:
    max_loss_per_setup_pct: 2.0
    daily_loss_limit_pct: 10.0
  features:
    enable_pyramiding: true
  system:
    log_level: INFO

# Per-pair configuration
pairs:
  BTC_ETH:
    name: BTC_ETH
    primary_symbol: BTCUSD
    secondary_symbol: ETHUSD

    trading:
      entry_threshold: 1.0
      exit_threshold: 0.5

    risk:
      max_loss_per_setup_pct: 1.0
      daily_loss_limit_pct: 2.0

    # ... more settings
```

## Configuration Precedence

```
1. .env file (environment variables)    [HIGHEST]
2. unified.yaml (runtime config)
3. defaults.py (code defaults)          [LOWEST]
```

## Key Features

✅ **Single source of truth** - One YAML file for all settings
✅ **Type-safe** - Dataclasses with IDE autocomplete
✅ **Per-pair config** - Different settings for each pair
✅ **Dynamic symbols** - Specs loaded from MT5 (always in sync)
✅ **Clear precedence** - .env > YAML > defaults
✅ **Backward compatible** - Old configs still work (with warnings)

## Migration Guide

See: [CONFIG_MIGRATION_GUIDE.md](../docs/CONFIG_MIGRATION_GUIDE.md)

**TL;DR:**

OLD:
```python
from config.settings import get_config
from config.trading_settings import TradingSettingsManager
```

NEW:
```python
from config.manager import get_config
```

## API Reference

### ConfigManager

```python
config = get_config()

# Get configurations
pair = config.get_pair('BTC_ETH')              # PairConfig
symbol = config.get_symbol('BTCUSD')            # SymbolSpec
risk = config.get_global_risk()                 # RiskParameters
features = config.get_global_features()         # FeatureFlags

# Modify configurations
config.add_pair(new_pair)                       # Add new pair
config.update_pair('BTC_ETH', updates)          # Update pair
config.reload()                                 # Reload from disk
```

### PairConfig Structure

```python
pair.name                    # Pair name
pair.primary_symbol          # Primary symbol
pair.secondary_symbol        # Secondary symbol
pair.description             # Description
pair.risk_level              # LOW, MEDIUM, HIGH

# Nested configurations (type-safe)
pair.trading                 # TradingParameters
  .entry_threshold
  .exit_threshold
  .max_positions

pair.risk                    # RiskParameters
  .max_loss_per_setup_pct
  .daily_loss_limit_pct

pair.model                   # ModelParameters
  .rolling_window_size
  .update_interval

pair.rebalancer              # RebalancerParameters
  .scale_interval
  .initial_fraction

pair.features                # FeatureFlags
  .enable_pyramiding
  .enable_volume_rebalancing

pair.system                  # SystemParameters
  .magic_number
  .log_level

pair.costs                   # TransactionCosts
  .commission_per_lot
  .spread_bps
```

## Environment Variables (.env)

**MT5 credentials:**
```bash
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo

# Optional overrides
LOG_LEVEL=INFO
DAILY_LOSS_LIMIT_PCT=10.0
```

**Never commit .env to git!**

## Testing

```bash
# Test configuration system
python -m config.manager

# Expected output:
# ================================================================================
# UNIFIED CONFIGURATION SYSTEM TEST
# ================================================================================
# [CONFIG] Configuration Status:
#    Config file: asset\config\unified.yaml
#    Config exists: True
# ...
# TEST PASSED - Unified config system working!
```

## Examples

### Example 1: Get Pair Configuration

```python
from config.manager import get_config

config = get_config()
pair = config.get_pair('BTC_ETH')

print(f"Pair: {pair.name}")
print(f"Symbols: {pair.primary_symbol}/{pair.secondary_symbol}")
print(f"Entry threshold: {pair.trading.entry_threshold}")
print(f"Risk level: {pair.risk_level}")
```

### Example 2: Get Symbol Specs

```python
from config.manager import get_config

config = get_config()

# Load from MT5 (always fresh!)
btc_spec = config.get_symbol('BTCUSD')
print(f"BTC contract size: {btc_spec.contract_size}")
print(f"BTC min lot: {btc_spec.min_lot}")
```

### Example 3: Add New Pair

```python
from config.manager import get_config
from config.models import PairConfig, TradingParameters, RiskParameters

config = get_config()

# Create new pair
new_pair = PairConfig(
    name='EUR_GBP',
    primary_symbol='EURUSD',
    secondary_symbol='GBPUSD',
    trading=TradingParameters(
        entry_threshold=2.0,
        exit_threshold=0.5,
    ),
    risk=RiskParameters(
        max_loss_per_setup_pct=2.0,
        daily_loss_limit_pct=10.0,
    )
)

# Add to config (saves to YAML)
config.add_pair(new_pair)
```

### Example 4: Update Pair Settings

```python
from config.manager import get_config

config = get_config()

# Update nested settings
config.update_pair('BTC_ETH', {
    'trading.entry_threshold': 2.5,  # More conservative
    'risk.daily_loss_limit_pct': 5.0,  # Tighter limit
})
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Config file not found | Auto-created on first run |
| Symbol not found | Check MT5 running, symbol in Market Watch |
| DeprecationWarning | Update imports to `config.manager` |
| Changes not loading | Call `config.reload()` |

## Files

| File | Status | Description |
|------|--------|-------------|
| `manager.py` | ✅ **USE THIS** | Main configuration manager |
| `models.py` | ✅ Active | Type-safe dataclasses |
| `defaults.py` | ✅ Active | Default values |
| `settings.py` | ⚠️ Deprecated | Old config system |
| `trading_settings.py` | ⚠️ Deprecated | Old trading settings |
| `risk_limits.py` | ⚠️ Deprecated | Old risk limits |
| `instruments.py` | ⚠️ Deprecated | Hardcoded symbols |

## Support

- Migration guide: [CONFIG_MIGRATION_GUIDE.md](../docs/CONFIG_MIGRATION_GUIDE.md)
- Source code: `config/manager.py`
- Models: `config/models.py`
- Defaults: `config/defaults.py`

---

**Version:** 2.0.0 (Unified Config System)
**Last Updated:** 2026-01-20
