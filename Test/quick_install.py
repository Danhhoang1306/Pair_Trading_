"""
Quick Install - Install all required dependencies
Run this to install everything needed
"""

import subprocess
import sys

print("="*70)
print("QUICK INSTALL - Installing all dependencies")
print("="*70)
print()

packages = [
    "PyQt6>=6.6.0",
    "MetaTrader5>=5.0.45",
    "numpy>=1.24.0",
    "pandas>=2.0.0",
    "scipy>=1.10.0",
    "statsmodels>=0.14.0",
    "scikit-learn>=1.3.0",
    "arch>=6.2.0",  # CRITICAL for volatility models
    "PyYAML>=6.0",
    "python-dateutil>=2.8.0",
    "pytz>=2023.3",
]

print(f"Installing {len(packages)} packages...")
print()

failed = []
for i, package in enumerate(packages, 1):
    package_name = package.split(">=")[0]
    print(f"[{i}/{len(packages)}] Installing {package_name}...", end=" ")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("✅")
        else:
            print(f"❌")
            failed.append(package_name)
            
    except Exception as e:
        print(f"❌ {e}")
        failed.append(package_name)

print()
print("="*70)

if failed:
    print(f"❌ FAILED TO INSTALL ({len(failed)}):")
    for pkg in failed:
        print(f"   - {pkg}")
    print()
    print("Try installing manually:")
    print(f"   pip install {' '.join(failed)}")
else:
    print("✅ ALL PACKAGES INSTALLED!")
    print()
    print("Next step:")
    print("   python launch_gui.py")

print("="*70)
