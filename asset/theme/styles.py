"""
PyCharm Darcula Theme - Style Definitions
Professional dark theme matching JetBrains IDEs
"""

from pathlib import Path

# ========================================
# COLOR CONSTANTS (for programmatic use)
# ========================================

# Background Colors
BG_DARKEST = "#1E1E1E"      # Deepest background
BG_DARKER = "#2B2B2B"       # Editor background
BG_DARK = "#3C3F41"         # Panel background
BG_MEDIUM = "#4E5254"       # Hover state
BG_LIGHT = "#5E6163"        # Selection
BG_LIGHTER = "#6E7173"      # Light selection

# Text Colors
TEXT_DISABLED = "#787878"   # Disabled text
TEXT_SECONDARY = "#8C8C8C"  # Secondary text
TEXT_NORMAL = "#A9B7C6"     # Normal text
TEXT_COMMENT = "#BBBBBB"    # Comments
TEXT_KEYWORD = "#CCCCCC"    # Keywords
TEXT_BRIGHT = "#FFFFFF"     # Bright text

# Border Colors
BORDER_DARK = "#323232"     # Dark borders
BORDER_MEDIUM = "#4B4B4B"   # Medium borders
BORDER_LIGHT = "#646464"    # Light borders

# Accent Colors
ACCENT_BLUE = "#3592C4"     # Primary accent (links, focus)
ACCENT_BLUE_HOVER = "#4A9ECD"  # Hover state
ACCENT_BLUE_DARK = "#2A6F9A"   # Dark variant

ACCENT_ORANGE = "#CC7832"   # Secondary accent (warnings)
ACCENT_YELLOW = "#FFC66D"   # Highlights
ACCENT_GREEN = "#6A8759"    # Success states
ACCENT_RED = "#BC3F3C"      # Error states
ACCENT_PURPLE = "#9876AA"   # Special items

# Status Colors
STATUS_SUCCESS = "#499C54"  # Green
STATUS_WARNING = "#C57825"  # Orange
STATUS_ERROR = "#BC3F3C"    # Red
STATUS_INFO = "#3592C4"     # Blue

# Chart Colors (for trading)
CHART_BULL = "#6A8759"      # Green (bullish)
CHART_BEAR = "#BC3F3C"      # Red (bearish)
CHART_NEUTRAL = "#A9B7C6"   # Gray (neutral)
CHART_GRID = "#3C3F41"      # Grid lines

# Selection Colors
SELECTION_BG = "#214283"    # Selection background
SELECTION_INACTIVE = "#3E4346"  # Inactive selection

# Scrollbar
SCROLLBAR_BG = "#3C3F41"    # Track
SCROLLBAR_THUMB = "#5E6163" # Thumb
SCROLLBAR_HOVER = "#6E7173" # Hover


# ========================================
# LOAD STYLESHEET FROM CSS FILE
# ========================================

def load_darcula_stylesheet() -> str:
    """Load Darcula theme CSS from file"""
    css_file = Path(__file__).parent / 'darcula_theme.css'
    try:
        with open(css_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: {css_file} not found, using fallback theme")
        return ""


# Load the stylesheet
DARCULA_THEME_QSS = load_darcula_stylesheet()


# ========================================
# UTILITY FUNCTIONS
# ========================================

def get_status_color(status: str) -> str:
    """Get color for status indicators"""
    colors = {
        'success': STATUS_SUCCESS,
        'error': STATUS_ERROR,
        'warning': STATUS_WARNING,
        'info': STATUS_INFO,
        'positive': CHART_BULL,
        'negative': CHART_BEAR,
        'neutral': CHART_NEUTRAL
    }
    return colors.get(status.lower(), TEXT_NORMAL)


def get_pnl_color(value: float) -> str:
    """Get color based on P&L value"""
    if value > 0:
        return CHART_BULL
    elif value < 0:
        return CHART_BEAR
    else:
        return CHART_NEUTRAL


def apply_theme(widget):
    """Apply Darcula theme to a Qt widget"""
    widget.setStyleSheet(DARCULA_THEME_QSS)


# ========================================
# EXPORT
# ========================================

__all__ = [
    # Colors
    'BG_DARKEST', 'BG_DARKER', 'BG_DARK', 'BG_MEDIUM', 'BG_LIGHT',
    'TEXT_DISABLED', 'TEXT_SECONDARY', 'TEXT_NORMAL', 'TEXT_COMMENT', 
    'TEXT_KEYWORD', 'TEXT_BRIGHT',
    'BORDER_DARK', 'BORDER_MEDIUM', 'BORDER_LIGHT',
    'ACCENT_BLUE', 'ACCENT_ORANGE', 'ACCENT_YELLOW', 'ACCENT_GREEN',
    'ACCENT_RED', 'ACCENT_PURPLE',
    'STATUS_SUCCESS', 'STATUS_WARNING', 'STATUS_ERROR', 'STATUS_INFO',
    'CHART_BULL', 'CHART_BEAR', 'CHART_NEUTRAL', 'CHART_GRID',
    # Stylesheet
    'DARCULA_THEME_QSS',
    # Functions
    'get_status_color', 'get_pnl_color', 'apply_theme'
]
