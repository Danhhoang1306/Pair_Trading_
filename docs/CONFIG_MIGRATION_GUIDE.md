# Configuration System Migration Guide

## Overview

The Pair Trading Pro configuration system has been unified to eliminate fragmentation and provide a single source of truth for all settings.

## What Changed?

### Before (OLD - Fragmented)

Configuration was scattered across multiple files:

```
.env.example               # Environment variables
config/settings.py         # PairConfig, RiskConfig
config/trading_settings.py # TradingSettings
config/risk_limits.py      # RISK_LIMITS dict
config/instruments.py      # Hardcoded symbol specs
asset/config/symbols_pairs.yaml  # Symbol definitions
asset/config/trading_settings.yaml  # Runtime settings
```

**Problems:**
- ❌ 5+ different config files
- ❌ Duplicate settings
- ❌ Unclear precedence
- ❌ Hardcoded symbol specs (out of sync with broker)
- ❌ No type safety

### After (NEW - Unified)

All configuration in one place:

```
.env                       # MT5 credentials (not committed)
asset/config/unified.yaml  # SINGLE config file
config/manager.py          # ConfigManager (singleton)
config/models.py           # Type-safe dataclasses
config/defaults.py         # Default values
```

**Benefits:**
- ✅ Single YAML file for all settings
- ✅ Clear precedence: .env > YAML > defaults
- ✅ Type-safe with dataclasses
- ✅ Symbol specs loaded from MT5 (always in sync)
- ✅ Per-pair configuration
- ✅ Backward compatible

## Configuration Precedence

Settings are loaded in this order (highest priority first):

```
1. Environment Variables (.env file)    [HIGHEST PRIORITY]
   └─ MT5 credentials, log level, etc.

2. YAML Configuration (unified.yaml)
   └─ Pair settings, risk params, features

3. Code Defaults (defaults.py)          [LOWEST PRIORITY]
   └─ Fallback values if not specified
```

## Migration Steps

### Step 1: Update Imports

**OLD:**
```python
from config.settings import get_config
from config.trading_settings import TradingSettingsManager
from config.risk_limits import RISK_LIMITS
from config.instruments import INSTRUMENTS
```

**NEW:**
```python
from config.manager import get_config
```

That's it! One import instead of four.

### Step 2: Update Configuration Access

#### Getting Pair Configuration

**OLD:**
```python
# Old fragmented approach
from config.settings import get_config
config_mgr = get_config()
pair = config_mgr.get_pair('BTC_ETH')

# Access nested settings
entry_threshold = pair.entry_threshold
risk_pct = pair.max_risk_pct
```

**NEW:**
```python
from config.manager import get_config

config = get_config()
pair = config.get_pair('BTC_ETH')

# Type-safe access to nested settings
entry_threshold = pair.trading.entry_threshold
risk_pct = pair.risk.max_loss_per_setup_pct
```

#### Getting Symbol Specifications

**OLD:**
```python
# Hardcoded specs (out of sync!)
from config.instruments import INSTRUMENTS
gold_spec = INSTRUMENTS['gold']
contract_size = gold_spec['contract_size']  # Could be wrong!
```

**NEW:**
```python
# Always fresh from MT5
from config.manager import get_config

config = get_config()
symbol_spec = config.get_symbol('XAUUSD')
contract_size = symbol_spec.contract_size  # Always correct!
```

#### Getting Risk Parameters

**OLD:**
```python
from config.risk_limits import RISK_LIMITS

max_daily_loss = RISK_LIMITS['max_daily_loss']
max_drawdown = RISK_LIMITS['max_drawdown_limit']
```

**NEW:**
```python
from config.manager import get_config

config = get_config()
pair = config.get_pair('BTC_ETH')

# Per-pair risk settings
max_daily_loss = pair.risk.daily_loss_limit_pct
max_drawdown = pair.risk.max_drawdown_pct

# Or global defaults
global_risk = config.get_global_risk()
default_daily_loss = global_risk.daily_loss_limit_pct
```

### Step 3: Update Configuration File

**OLD files (DEPRECATED):**
- `asset/config/trading_settings.yaml` - Delete or ignore
- `asset/config/symbols_pairs.yaml` - Delete or ignore

**NEW file:**
- `asset/config/unified.yaml` - Single source of truth

#### Example: Adding a New Pair

**In unified.yaml:**
```yaml
pairs:
  MY_NEW_PAIR:
    name: MY_NEW_PAIR
    primary_symbol: EURUSD
    secondary_symbol: GBPUSD
    description: 'EUR/GBP forex pair'
    risk_level: MEDIUM

    trading:
      entry_threshold: 2.0
      exit_threshold: 0.5
      stop_loss_zscore: 3.5
      max_positions: 10
      volume_multiplier: 1.0

    model:
      rolling_window_size: 1000
      update_interval: 60
      hedge_drift_threshold: 0.05

    risk:
      max_loss_per_setup_pct: 2.0
      max_total_unrealized_loss_pct: 5.0
      daily_loss_limit_pct: 10.0
      # ... rest of settings

    # ... other sections
```

**No code changes needed!** Just reload:
```python
from config.manager import reload_config
reload_config()
```

## Common Migration Patterns

### Pattern 1: Flat Config → Nested Config

**OLD:**
```python
config = {
    'entry_threshold': 2.0,
    'max_risk_pct': 2.0,
    'rolling_window_size': 1000,
    # All mixed together
}
```

**NEW:**
```python
pair = config.get_pair('BTC_ETH')

# Organized by category
trading_params = pair.trading  # entry_threshold, etc.
risk_params = pair.risk         # max_loss_per_setup_pct, etc.
model_params = pair.model       # rolling_window_size, etc.
```

### Pattern 2: Global Settings → Per-Pair Settings

**OLD:**
```python
# One size fits all
settings = TradingSettingsManager()
entry_threshold = settings.settings.entry_threshold
# Same for all pairs!
```

**NEW:**
```python
config = get_config()

# Different settings per pair
btc_eth = config.get_pair('BTC_ETH')
btc_entry = btc_eth.trading.entry_threshold  # 1.0 (aggressive)

xau_xag = config.get_pair('XAU_XAG')
gold_entry = xau_xag.trading.entry_threshold  # 2.0 (conservative)
```

### Pattern 3: Hardcoded Symbols → Dynamic Loading

**OLD:**
```python
# Hardcoded - wrong if broker changes!
GOLD_CONTRACT_SIZE = 100.0
```

**NEW:**
```python
# Always fresh from MT5
config = get_config()
gold_spec = config.get_symbol('XAUUSD')
contract_size = gold_spec.contract_size  # Current value from broker
```

## API Reference

### ConfigManager

```python
from config.manager import get_config

config = get_config()  # Singleton instance
```

**Methods:**

| Method | Description | Returns |
|--------|-------------|---------|
| `get_pair(name)` | Get pair configuration | `PairConfig` or `None` |
| `get_all_pairs()` | Get all pairs | `Dict[str, PairConfig]` |
| `get_symbol(symbol)` | Get symbol spec from MT5 | `SymbolSpec` or `None` |
| `get_mt5_config()` | Get MT5 connection config | `MT5Config` |
| `get_global_risk()` | Get global risk defaults | `RiskParameters` |
| `get_global_features()` | Get global feature flags | `FeatureFlags` |
| `add_pair(pair)` | Add new pair | None (saves to YAML) |
| `update_pair(name, updates)` | Update pair settings | None (saves to YAML) |
| `reload()` | Reload from disk | None |

### PairConfig Structure

```python
pair = config.get_pair('BTC_ETH')

# Access nested configurations
pair.name                    # str: 'BTC_ETH'
pair.primary_symbol          # str: 'BTCUSD'
pair.secondary_symbol        # str: 'ETHUSD'
pair.description             # str: Description
pair.risk_level              # str: 'LOW', 'MEDIUM', 'HIGH'

# Nested configs (type-safe dataclasses)
pair.trading                 # TradingParameters
pair.model                   # ModelParameters
pair.risk                    # RiskParameters
pair.rebalancer              # RebalancerParameters
pair.features                # FeatureFlags
pair.system                  # SystemParameters
pair.costs                   # TransactionCosts
```

### Example: Complete Access Pattern

```python
from config.manager import get_config

# Initialize
config = get_config()

# Get pair
pair = config.get_pair('BTC_ETH')

# Trading parameters
entry_threshold = pair.trading.entry_threshold
exit_threshold = pair.trading.exit_threshold
max_positions = pair.trading.max_positions

# Risk parameters
max_loss_per_setup = pair.risk.max_loss_per_setup_pct
daily_loss_limit = pair.risk.daily_loss_limit_pct

# Model parameters
window_size = pair.model.rolling_window_size
update_interval = pair.model.update_interval

# Feature flags
enable_pyramiding = pair.features.enable_pyramiding
enable_rebalancing = pair.features.enable_volume_rebalancing

# Get symbol specs from MT5
primary_spec = config.get_symbol(pair.primary_symbol)
contract_size = primary_spec.contract_size
min_lot = primary_spec.min_lot
```

## Backward Compatibility

All old config files are still present but marked as **DEPRECATED**. They will show warnings:

```python
# Old import
from config.settings import get_config

# Output:
# DeprecationWarning: config.settings is deprecated. Use config.manager instead.
```

The old config files continue to work for now, but should be migrated to the new system.

## Environment Variables (.env)

**MT5 credentials should NEVER be in YAML files!**

Always use `.env` file:

```bash
# .env (NOT committed to git!)
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo

# Optional overrides
LOG_LEVEL=INFO
DAILY_LOSS_LIMIT_PCT=10.0
MAX_RISK_PCT=2.0
```

## Testing Your Migration

Run the test script:

```bash
python -m config.manager
```

Expected output:
```
================================================================================
UNIFIED CONFIGURATION SYSTEM TEST
================================================================================

[CONFIG] Configuration Status:
   Config file: asset\config\unified.yaml
   Config exists: True

[MT5] MT5 Configuration:
   Login: Not set (use .env)
   Server: Not set (use .env)

[PAIRS] Configured Pairs:
   BTC_ETH:
      Symbols: BTCUSD/ETHUSD
      Entry threshold: 1.0
      Risk per setup: 1.0%
      Risk level: HIGH
   # ... more pairs

================================================================================
TEST PASSED - Unified config system working!
================================================================================
```

## Troubleshooting

### Issue: "Config file not found"

**Solution:** Config file will be auto-created with defaults on first run.

### Issue: "Symbol not found in MT5"

**Solution:**
1. Check MT5 is running and logged in
2. Verify symbol name (case-sensitive)
3. Add symbol to Market Watch in MT5

### Issue: "DeprecationWarning" messages

**Solution:** Migrate imports to new system:
- OLD: `from config.settings import get_config`
- NEW: `from config.manager import get_config`

### Issue: "Config not loading my changes"

**Solution:**
```python
from config.manager import reload_config
reload_config()  # Force reload from disk
```

## Summary

| Aspect | OLD System | NEW System |
|--------|-----------|------------|
| Config Files | 5+ files | 1 YAML file |
| Symbol Specs | Hardcoded | From MT5 |
| Type Safety | Dicts | Dataclasses |
| Precedence | Unclear | .env > YAML > defaults |
| Per-Pair Config | Limited | Full support |
| Migration | N/A | Backward compatible |

## Next Steps

1. ✅ Read this guide
2. ✅ Update imports in your code
3. ✅ Test with `python -m config.manager`
4. ✅ Migrate pair configurations to `unified.yaml`
5. ✅ Remove old config file imports
6. ✅ Enjoy simpler, type-safe configuration!

## Support

For questions or issues:
- Check `config/manager.py` source code
- Review `config/models.py` for dataclass structures
- See `config/defaults.py` for default values
- Read `asset/config/unified.yaml` for examples

---

**Last Updated:** 2026-01-20
**Version:** 2.0.0
