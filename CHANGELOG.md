# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2024-01-15

### Added
- **3-Layer Risk Management System**
  - Per-Setup Loss Limit: Max loss allowed for each individual setup
  - Total Portfolio Loss Limit: Max total unrealized loss across all positions
  - Daily Loss Limit: Max total loss per day (realized + unrealized)
- **Trading Lock Manager**: Automatic trading lock when risk limits are breached
- **State Persistence**: Positions and state survive system restarts
- **Hybrid Rebalancer**: Combined pyramiding and hedge adjustment logic
- **GUI Dashboard**: Real-time charts, risk monitoring, and controls
- **Backtest Engine**: Historical testing with MT5 data
- **Multi-pair Support**: Trade multiple pairs simultaneously (Crypto, Indices)

### Changed
- Refactored executor architecture (entry, exit, pyramiding, volume rebalancer)
- Improved hedge ratio calculation with drift detection
- Enhanced signal generator with cooldown mechanism
- Centralized configuration system with YAML support

### Fixed
- Continuous entry bug causing duplicate positions
- Margin alert false positives
- Z-score calculation accuracy
- Position synchronization with MT5

### Removed
- Legacy executor implementations
- Deprecated configuration parameters

## [1.5.0] - 2024-01-01

### Added
- Pyramiding functionality with configurable scale intervals
- Hedge adjustment when ratio drifts beyond threshold
- Entry cooldown to prevent duplicate entries
- Z-score history tracking and monitoring

### Changed
- Improved position sizing with Kelly Criterion
- Enhanced logging with color support
- Better error handling in MT5 communication

### Fixed
- Race conditions in multi-threaded execution
- Memory leaks in data manager
- GUI freezing during heavy operations

## [1.0.0] - 2023-12-01

### Added
- Initial release
- Basic pair trading with Z-score signals
- MT5 integration for order execution
- Simple GUI interface
- Position monitoring and tracking
- Basic risk management

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 2.0.0 | 2024-01-15 | 3-layer risk, state persistence, backtest |
| 1.5.0 | 2024-01-01 | Pyramiding, hedge adjustment |
| 1.0.0 | 2023-12-01 | Initial release |
