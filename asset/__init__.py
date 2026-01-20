"""
Asset Package
Centralized configuration, theme, and state files

Structure:
  asset/
  ├── config/     - Configuration files (YAML)
  │   ├── trading_settings.yaml
  │   ├── default_config.yaml
  │   └── symbols_pairs.yaml
  ├── theme/      - UI theme files
  │   ├── styles.py
  │   └── darcula_theme.css
  └── state/      - Runtime state files (JSON)
      ├── spread_states.json
      └── trading_lock.json
"""

# Re-export theme for backward compatibility
from .theme import *

__version__ = '1.0.0'
