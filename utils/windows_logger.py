"""
Windows-Safe Logging Configuration
"""

import sys
import logging


def setup_windows_safe_logging():
    """
    Setup logging that works on Windows console
    Avoids UnicodeEncodeError by using ASCII-safe characters
    """
    # Force UTF-8 encoding for stdout/stderr on Windows
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Add file handler with UTF-8 encoding
    file_handler = logging.FileHandler('trading.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    logging.getLogger().addHandler(file_handler)


# Unicode-safe replacements for common symbols
SYMBOLS = {
    'check': '[OK]',
    'cross': '[X]',
    'arrow_right': '->',
    'arrow_left': '<-',
    'bullet': '*',
}
