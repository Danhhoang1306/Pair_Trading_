# Asset Directory

Centralized directory for configuration, theme, and runtime state files.

## Structure

```
asset/
├── config/               # Configuration files (YAML)
│   ├── trading_settings.yaml    # Main trading settings (single source of truth)
│   ├── default_config.yaml      # Default configuration template
│   └── symbols_pairs.yaml       # Trading symbols configuration
│
├── theme/                # UI theme files
│   ├── __init__.py              # Theme package exports
│   ├── styles.py                # Color constants and utilities
│   └── darcula_theme.css        # PyCharm Darcula theme stylesheet
│
├── state/                # Runtime state files (JSON)
│   ├── spread_states.json       # SimpleUnifiedExecutor state (last_z, next_z)
│   ├── last_z_entry.json        # Legacy EntryCooldownManager state
│   ├── trading_lock.json        # Trading lock state
│   └── grid_state.json          # Grid trading state
│
├── __init__.py           # Package exports (re-exports theme)
├── README.md             # This file
└── .gitignore            # Ignore runtime state files
```

## config/ - Configuration Files

### `trading_settings.yaml`
Main trading configuration - **single source of truth**.

Used by:
- GUI settings panel
- HybridRebalancer
- SimpleUnifiedExecutor
- EntryCooldownManager

### `symbols_pairs.yaml`
Trading pair symbol configuration.

## theme/ - UI Theme

### `styles.py`
Python color constants and utility functions for the Darcula theme.

### `darcula_theme.css`
Qt stylesheet for PyCharm Darcula dark theme.

## state/ - Runtime State Files

### `spread_states.json`
SimpleUnifiedExecutor state persistence.

**Format:**
```json
{
  "spreads": {
    "spread-uuid": {
      "spread_id": "spread-uuid",
      "side": "LONG",
      "last_z_entry": -2.5,
      "next_z_entry": -3.0,
      "entry_count": 1,
      "total_primary_lots": 0.0,
      "total_secondary_lots": 0.0
    }
  },
  "last_updated": "2026-01-16T22:00:00"
}
```

### `last_z_entry.json`
Legacy EntryCooldownManager state (for backward compatibility).

### `trading_lock.json`
Trading lock state for daily loss limit management.

### `grid_state.json`
Grid trading strategy state.

## Manual Operations

### View state:
```bash
cat asset/state/spread_states.json
```

### Reset state (allow new entries):
```bash
rm asset/state/spread_states.json
```

## Safety

- Files are auto-created if missing
- Corrupt files are ignored (starts fresh)
- State files should not be committed to git
