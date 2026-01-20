"""
Main Application - NAS100/SP500 Pair Trading System
Multi-threaded real-time trading system
IDENTICAL to main.py but with NAS100.r/SP500.r symbols
"""

import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import threading
import queue
import time
import signal
from datetime import datetime
import logging

from core.data_manager import DataManager
from core.mt5_trade_executor import MT5TradeExecutor
from core.realtime_market_data import RealTimeMarketData
from utils.data_preprocessor import DataPreprocessor
from utils.zscore_monitor import ZScoreMonitor
from models import HedgeRatioCalculator
from risk import PositionSizer, DrawdownMonitor, RiskChecker
from strategy import (SignalGenerator, OrderManager, PositionTracker,
                      SignalType, OrderStatus)
from strategy.hybrid_rebalancer import HybridRebalancer
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


# =========================================================================
# SYMBOLS CONFIGURATION - ONLY DIFFERENCE FROM main.py
# =========================================================================
PRIMARY_SYMBOL = 'NAS100.r'      # NASDAQ 100
SECONDARY_SYMBOL = 'SP500.r'     # S&P 500
PRIMARY_CONTRACT_SIZE = 1        # 1 point = $1
SECONDARY_CONTRACT_SIZE = 1      # 1 point = $1
MAGIC_NUMBER = 234001            # Different magic number for indices
# =========================================================================


class TradingSystem:
    """Multi-threaded pair trading system"""

    def __init__(self, account_balance: float = 100000,
                 update_interval: int = 60,
                 max_positions: int = 10,
                 volume_multiplier: float = 10):
        """
        Initialize trading system

        Args:
            account_balance: Starting account balance
            update_interval: Data update interval (seconds)
            max_positions: Maximum concurrent positions
            volume_multiplier: Volume multiplier for all trades
        """
        self.account_balance = account_balance
        self.update_interval = update_interval
        self.max_positions = max_positions
        self.volume_multiplier = volume_multiplier

        # Threading
        self.running = False
        self.threads = []
        self.lock = threading.RLock()

        # Queues
        self.data_queue = queue.Queue(maxsize=10)
        self.signal_queue = queue.Queue(maxsize=10)

        # Components
        logger.info("Initializing components...")
        self.data_manager = DataManager()
        self.trade_executor = MT5TradeExecutor(
            magic_number=MAGIC_NUMBER,
            volume_multiplier=volume_multiplier
        )
        self.preprocessor = DataPreprocessor()
        self.hedge_calculator = HedgeRatioCalculator()

        # Real-time market data manager
        self.market_data = RealTimeMarketData(
            data_manager=self.data_manager,
            preprocessor=self.preprocessor,
            hedge_calculator=self.hedge_calculator,
            historical_update_interval=3600,
            rolling_window_size=1000  # Sync with config
        )

        self.position_sizer = PositionSizer(account_balance)
        self.drawdown_monitor = DrawdownMonitor(account_balance)
        self.risk_checker = RiskChecker()
        self.signal_generator = SignalGenerator()
        self.order_manager = OrderManager()
        self.position_tracker = PositionTracker()
        self.rebalancer = HybridRebalancer(
            scale_interval=0.1,  # Sync with config
            max_zscore=3.5,
            initial_fraction=0.33,  # Sync with config
            hedge_drift_threshold=0.05,
            min_adjustment_interval=3600,
            enable_hedge_adjustment=True
        )
        self.zscore_monitor = ZScoreMonitor(max_history=200)

        # State
        self.current_signal = None
        self.current_snapshot = None
        self.current_hedge_ratio = None
        self.last_update_time = None

        # MT5 position tracking
        self.mt5_tickets = {}

        logger.info(f"System initialized (balance=${account_balance:,.2f})")
        logger.info(f"Trading pair: {PRIMARY_SYMBOL} / {SECONDARY_SYMBOL}")

    def start(self):
        """Start all threads"""
        logger.info("Starting system...")
        self.running = True

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Thread configuration
        threads_config = [
            ("Data", self._data_thread),
            ("Signal", self._signal_thread),
            ("Execution", self._execution_thread),
            ("Monitor", self._monitor_thread)
        ]

        # Start threads
        for name, target in threads_config:
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self.threads.append(thread)
            logger.info(f"Started {name} thread")

        logger.info("All threads started")

    def stop(self):
        """Stop all threads"""
        logger.info("Stopping system...")
        self.running = False

        for thread in self.threads:
            thread.join(timeout=5)

        self.data_manager.connector.shutdown()
        self.trade_executor.shutdown()
        logger.info("System stopped")

    def _signal_handler(self, signum, frame):
        """Handle system signals"""
        logger.info(f"\nReceived signal {signum}")
        self.stop()
        sys.exit(0)

    def _data_thread(self):
        """Data fetching thread"""
        logger.info("Data thread started")

        logger.info("Bootstrapping rolling window with historical data...")
        try:
            self.market_data.bootstrap_window(
                days=30,
                primary_symbol=PRIMARY_SYMBOL,
                secondary_symbol=SECONDARY_SYMBOL,
                primary_contract_size=PRIMARY_CONTRACT_SIZE,
                secondary_contract_size=SECONDARY_CONTRACT_SIZE
            )
            logger.info("Rolling window ready - starting real-time updates")

            logger.info("Fetching initial snapshot...")
            initial_snapshot = self.market_data.get_realtime_snapshot()

            if initial_snapshot:
                self.current_snapshot = initial_snapshot
                logger.info(f"Initial market state: {initial_snapshot}")

                primary_vol, secondary_vol = self.market_data.get_volatility()

                initial_data = {
                    'timestamp': initial_snapshot.timestamp,
                    'snapshot': initial_snapshot,
                    'current_primary_price': initial_snapshot.primary_bid,
                    'current_secondary_price': initial_snapshot.secondary_bid,
                    'current_zscore': initial_snapshot.zscore,
                    'primary_vol': primary_vol,
                    'secondary_vol': secondary_vol
                }

                try:
                    self.data_queue.put(initial_data, block=False)
                    logger.info("Initial snapshot queued for signal processing")
                except queue.Full:
                    logger.warning("Data queue full on initial snapshot")

        except Exception as e:
            logger.error(f"Bootstrap error: {e}")
            import traceback
            traceback.print_exc()
            self.running = False
            return

        logger.info(f"Starting continuous data updates (every {self.update_interval}s)...")

        while self.running:
            try:
                snapshot = self.market_data.get_realtime_snapshot()

                if snapshot is None:
                    logger.error("Failed to get market snapshot")
                    time.sleep(10)
                    continue

                primary_vol, secondary_vol = self.market_data.get_volatility()

                data = {
                    'timestamp': snapshot.timestamp,
                    'snapshot': snapshot,
                    'current_primary_price': snapshot.primary_bid,
                    'current_secondary_price': snapshot.secondary_bid,
                    'current_zscore': snapshot.zscore,
                    'primary_vol': primary_vol,
                    'secondary_vol': secondary_vol
                }

                try:
                    self.data_queue.put(data, block=False)
                    logger.debug(f"Rolling update: {snapshot}")
                    logger.debug(f"  Mean: {snapshot.spread_mean:.2f}, Std: {snapshot.spread_std:.2f}")
                except queue.Full:
                    logger.warning("Data queue full")

                self.last_update_time = datetime.now()
                self.current_snapshot = snapshot

                time.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Data thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)

    def _signal_thread(self):
        """Signal generation thread"""
        logger.info("Signal thread started")

        while self.running:
            try:
                data = self.data_queue.get(timeout=5)

                with self.lock:
                    snapshot = data['snapshot']

                    open_positions = self.position_tracker.get_all_positions()
                    current_position = None

                    if open_positions:
                        primary_positions = [p for p in open_positions if p.symbol == PRIMARY_SYMBOL]
                        if primary_positions:
                            current_position = 'LONG' if primary_positions[0].side == 'LONG' else 'SHORT'

                    signal = self.signal_generator.generate_signal(
                        primary_price=snapshot.primary_bid,
                        secondary_price=snapshot.secondary_bid,
                        zscore=snapshot.zscore,
                        hedge_ratio=snapshot.hedge_ratio,
                        current_position=current_position
                    )

                    self.current_signal = signal

                    self.zscore_monitor.add(signal.zscore)

                    zscore_status = self.zscore_monitor.format_status()
                    logger.info(f"[MARKET] {zscore_status}")
                    logger.info(f"         {PRIMARY_SYMBOL}: ${snapshot.primary_bid:.2f} | "
                                f"{SECONDARY_SYMBOL}: ${snapshot.secondary_bid:.4f} | "
                                f"Signal: {signal.signal_type.value} | "
                                f"Window: {snapshot.window_size} bars")

                    if self.zscore_monitor.should_alert(threshold=0.3):
                        change = self.zscore_monitor.get_change()
                        logger.warning(f"[ALERT] Significant z-score change: {change:+.3f}")

                    if open_positions:
                        current_hedge_ratio = snapshot.hedge_ratio

                        pyramid_actions, hedge_adjustments = self.rebalancer.check_all_rebalancing(
                            current_zscore=snapshot.zscore,
                            current_hedge_ratio=current_hedge_ratio
                        )

                        for action in pyramid_actions:
                            logger.info(f"[PYRAMIDING] {action['reason']}")
                            try:
                                self.signal_queue.put({
                                    'signal': signal,
                                    'data': data,
                                    'rebalance': action
                                }, block=False)
                            except queue.Full:
                                logger.warning("Signal queue full")

                        for adjustment in hedge_adjustments:
                            logger.info(f"[HEDGE ADJUSTMENT] {adjustment.reason}")
                            try:
                                self.signal_queue.put({
                                    'signal': signal,
                                    'data': data,
                                    'hedge_adjustment': adjustment
                                }, block=False)
                            except queue.Full:
                                logger.warning("Signal queue full")

                    if signal.signal_type != SignalType.HOLD:
                        try:
                            self.signal_queue.put({
                                'signal': signal,
                                'data': data,
                                'rebalance': None
                            }, block=False)
                        except queue.Full:
                            logger.warning("Signal queue full")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Signal thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _execution_thread(self):
        """Execution thread"""
        logger.info("Execution thread started")

        while self.running:
            try:
                signal_data = self.signal_queue.get(timeout=5)
                signal = signal_data['signal']
                data = signal_data['data']
                rebalance = signal_data.get('rebalance')
                hedge_adjustment = signal_data.get('hedge_adjustment')

                with self.lock:
                    if rebalance and rebalance.get('type') == 'PYRAMIDING':
                        self._execute_pyramiding(rebalance, data)
                        continue

                    if hedge_adjustment:
                        self._execute_hedge_adjustment(hedge_adjustment, data)
                        continue

                    if len(self.position_tracker.positions) >= self.max_positions:
                        logger.warning(f"Max positions ({self.max_positions}) reached")
                        continue

                    primary_vol, secondary_vol = self.market_data.get_volatility()

                    pos_size_result = self.position_sizer.calculate_optimal(
                        win_rate=0.55,
                        avg_win=150,
                        avg_loss=100,
                        volatility=primary_vol
                    )

                    dd_metrics = self.drawdown_monitor.get_metrics()

                    snapshot = data['snapshot']

                    risk_result = self.risk_checker.check_trade(
                        position_size=pos_size_result.position_size,
                        account_balance=self.account_balance,
                        current_drawdown_pct=dd_metrics.current_drawdown_pct,
                        entry_price=snapshot.primary_bid,
                        stop_loss=snapshot.primary_bid * 0.98,
                        take_profit=snapshot.primary_bid * 1.02,
                        open_positions=len(self.position_tracker.positions)
                    )

                    if not risk_result.passed:
                        logger.warning(f"Risk check FAILED: {risk_result.reason}")
                        continue

                    if signal.signal_type in [SignalType.LONG_SPREAD, SignalType.SHORT_SPREAD]:
                        self._execute_entry(signal, data, pos_size_result)
                    elif signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
                        self._execute_exit(signal, data)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Execution thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _execute_entry(self, signal, data, pos_size_result):
        """Execute spread entry"""
        try:
            primary_value = self.account_balance * pos_size_result.position_size
            primary_quantity = primary_value / data['current_primary_price'] / PRIMARY_CONTRACT_SIZE

            primary_lots, secondary_lots = self.market_data.calculate_hedge_quantities(primary_quantity)

            side = 'LONG' if signal.signal_type == SignalType.LONG_SPREAD else 'SHORT'

            snapshot = data['snapshot']

            logger.info(f"=== EXECUTING {side} SPREAD (REAL-TIME) ===")
            logger.info(f"Market: {PRIMARY_SYMBOL} ${snapshot.primary_bid:.2f}, {SECONDARY_SYMBOL} ${snapshot.secondary_bid:.4f}")
            logger.info(f"Z-Score: {snapshot.zscore:.3f}")
            logger.info(f"Hedge Ratio: {snapshot.hedge_ratio:.4f}")
            logger.info(f"Position: {PRIMARY_SYMBOL} {primary_lots:.4f} lots, {SECONDARY_SYMBOL} {secondary_lots:.4f} lots")

            primary_result, secondary_result = self.trade_executor.place_spread_orders(
                primary_volume=primary_lots,
                secondary_volume=secondary_lots,
                side=side,
                primary_symbol=PRIMARY_SYMBOL,
                secondary_symbol=SECONDARY_SYMBOL
            )

            if not primary_result.success or not secondary_result.success:
                logger.error(f"Trade execution FAILED!")
                if not primary_result.success:
                    logger.error(f"  {PRIMARY_SYMBOL}: {primary_result.comment}")
                if not secondary_result.success:
                    logger.error(f"  {SECONDARY_SYMBOL}: {secondary_result.comment}")
                return

            logger.info(f"[MT5 SUCCESS] Orders filled:")
            logger.info(f"  {PRIMARY_SYMBOL}: {primary_result.volume} lots @ ${primary_result.price:.2f} (Ticket {primary_result.order_ticket})")
            logger.info(f"  {SECONDARY_SYMBOL}: {secondary_result.volume} lots @ ${secondary_result.price:.4f} (Ticket {secondary_result.order_ticket})")

            primary_order, secondary_order = self.order_manager.create_spread_orders(
                primary_result.volume, secondary_result.volume, side
            )

            self.order_manager.update_order_status(
                primary_order.order_id, OrderStatus.FILLED,
                primary_result.volume, primary_result.price
            )

            self.order_manager.update_order_status(
                secondary_order.order_id, OrderStatus.FILLED,
                secondary_result.volume, secondary_result.price
            )

            primary_pos, secondary_pos = self.position_tracker.open_spread_position(
                primary_result.volume, secondary_result.volume,
                primary_result.price, secondary_result.price,
                side, snapshot.hedge_ratio
            )

            self.mt5_tickets[primary_pos.position_id] = primary_result.order_ticket
            self.mt5_tickets[secondary_pos.position_id] = secondary_result.order_ticket

            spread_id = primary_pos.metadata.get('spread_id')
            if spread_id:
                try:
                    import pickle
                    from pathlib import Path

                    persist_dir = Path(__file__).parent / 'data' / 'positions'
                    persist_dir.mkdir(parents=True, exist_ok=True)

                    position_data = {
                        'spread_id': spread_id,
                        'side': side,
                        'primary_ticket': primary_result.order_ticket,
                        'secondary_ticket': secondary_result.order_ticket,
                        'primary_lots': primary_result.volume,
                        'secondary_lots': secondary_result.volume,
                        'primary_price': primary_result.price,
                        'secondary_price': secondary_result.price,
                        'entry_zscore': snapshot.zscore,
                        'hedge_ratio': snapshot.hedge_ratio,
                        'timestamp': datetime.now()
                    }

                    filepath = persist_dir / f"{spread_id}.pkl"
                    with open(filepath, 'wb') as f:
                        pickle.dump(position_data, f)

                    logger.info(f"[PERSISTENCE] Spread {spread_id[:8]} saved to disk")

                except Exception as e:
                    logger.warning(f"Failed to persist position: {e}")

            if spread_id:
                self.rebalancer.register_position(
                    spread_id=spread_id,
                    side=side,
                    entry_zscore=snapshot.zscore,
                    entry_hedge_ratio=snapshot.hedge_ratio,
                    primary_lots=primary_result.volume,
                    secondary_lots=secondary_result.volume,
                    total_position_size=pos_size_result.position_size
                )
                logger.info(f"[HYBRID REBALANCER] Position registered")
                logger.info(f"  Pyramiding: Enabled")
                logger.info(f"  Hedge adjustment: {'Enabled' if self.rebalancer.enable_hedge_adjustment else 'Disabled'}")

            logger.info(f"[SUCCESS] {side} SPREAD opened")

        except Exception as e:
            logger.error(f"Entry error: {e}")
            import traceback
            traceback.print_exc()

    def _execute_pyramiding(self, rebalance, data):
        """Execute pyramiding"""
        try:
            spread_id = rebalance['spread_id']
            side = rebalance['side']
            level = rebalance['level']
            position_size = rebalance['position_size']

            snapshot = data['snapshot']

            logger.info(f"[REBALANCE] Scaling into position {spread_id[:8]}")
            logger.info(f"  Z-score: {snapshot.zscore:.2f} → trigger: {level.zscore:.2f}")
            logger.info(f"  Adding: {position_size:.2%} of total position")

            primary_value = self.account_balance * position_size
            primary_quantity = primary_value / snapshot.primary_bid / PRIMARY_CONTRACT_SIZE

            primary_lots, secondary_lots = self.market_data.calculate_hedge_quantities(primary_quantity)

            logger.info(f"  {PRIMARY_SYMBOL}: +{primary_lots:.4f} lots")
            logger.info(f"  {SECONDARY_SYMBOL}: +{secondary_lots:.4f} lots")

            primary_result, secondary_result = self.trade_executor.place_spread_orders(
                primary_volume=primary_lots,
                secondary_volume=secondary_lots,
                side=side,
                primary_symbol=PRIMARY_SYMBOL,
                secondary_symbol=SECONDARY_SYMBOL
            )

            if not primary_result.success or not secondary_result.success:
                logger.error(f"Rebalance execution FAILED!")
                return

            logger.info(f"[MT5 SUCCESS] Rebalance orders filled:")
            logger.info(f"  {PRIMARY_SYMBOL}: {primary_result.volume} lots @ ${primary_result.price:.2f}")
            logger.info(f"  {SECONDARY_SYMBOL}: {secondary_result.volume} lots @ ${secondary_result.price:.4f}")

            self.rebalancer.mark_pyramiding_executed(
                spread_id=spread_id,
                zscore=level.zscore,
                primary_lots=primary_result.volume,
                secondary_lots=secondary_result.volume
            )

            primary_pos, secondary_pos = self.position_tracker.open_spread_position(
                primary_result.volume, secondary_result.volume,
                primary_result.price, secondary_result.price,
                side, snapshot.hedge_ratio
            )

            primary_pos.metadata['spread_id'] = spread_id
            secondary_pos.metadata['spread_id'] = spread_id

            self.mt5_tickets[primary_pos.position_id] = primary_result.order_ticket
            self.mt5_tickets[secondary_pos.position_id] = secondary_result.order_ticket

            logger.info(f"[SUCCESS] Rebalanced position {spread_id[:8]}")

        except Exception as e:
            logger.error(f"Rebalance error: {e}")
            import traceback
            traceback.print_exc()

    def _execute_hedge_adjustment(self, adjustment, data):
        """Execute hedge adjustment"""
        try:
            spread_id = adjustment.spread_id

            logger.info(f"[HEDGE ADJUSTMENT] Adjusting position {spread_id[:8]}")
            logger.info(f"  Reason: {adjustment.reason}")
            logger.info(f"  Old hedge: {adjustment.old_hedge:.4f}")
            logger.info(f"  New hedge: {adjustment.new_hedge:.4f}")
            logger.info(f"  Action: {adjustment.action} {adjustment.quantity:.4f} lots {adjustment.symbol}")

            if adjustment.action == 'BUY':
                result = self.trade_executor.place_order(
                    symbol=SECONDARY_SYMBOL,
                    volume=adjustment.quantity,
                    side='BUY'
                )
            else:
                result = self.trade_executor.place_order(
                    symbol=SECONDARY_SYMBOL,
                    volume=adjustment.quantity,
                    side='SELL'
                )

            if not result.success:
                logger.error(f"Hedge adjustment FAILED: {result.comment}")
                return

            logger.info(f"[MT5 SUCCESS] Hedge adjustment executed:")
            logger.info(f"  {result.volume} lots @ ${result.price:.4f} (Ticket {result.order_ticket})")

            self.rebalancer.mark_hedge_adjusted(
                spread_id=spread_id,
                adjustment=adjustment,
                executed_quantity=result.volume
            )

            positions = [p for p in self.position_tracker.get_all_positions()
                         if p.metadata.get('spread_id') == spread_id and p.symbol == adjustment.symbol]

            if positions:
                position = positions[0]

                if adjustment.action == 'BUY':
                    logger.info(f"  Updated {position.symbol} position")
                else:
                    logger.info(f"  Reduced {position.symbol} position")

            logger.info(f"[SUCCESS] Hedge adjustment complete")

        except Exception as e:
            logger.error(f"Hedge adjustment error: {e}")
            import traceback
            traceback.print_exc()

    def _execute_exit(self, signal, data):
        """Execute spread exit"""
        try:
            positions = self.position_tracker.get_all_positions()

            if not positions:
                return

            spread_ids = set()
            for pos in positions:
                if 'spread_id' in pos.metadata:
                    spread_ids.add(pos.metadata['spread_id'])

            for spread_id in spread_ids:
                logger.info(f"Closing spread {spread_id[:8]} on MT5...")

                spread_positions = [p for p in positions if p.metadata.get('spread_id') == spread_id]
                primary_pos = next((p for p in spread_positions if p.symbol == PRIMARY_SYMBOL), None)
                secondary_pos = next((p for p in spread_positions if p.symbol == SECONDARY_SYMBOL), None)

                if not primary_pos or not secondary_pos:
                    logger.error(f"Incomplete spread {spread_id[:8]}")
                    continue

                primary_ticket = self.mt5_tickets.get(primary_pos.position_id)
                secondary_ticket = self.mt5_tickets.get(secondary_pos.position_id)

                if not primary_ticket or not secondary_ticket:
                    logger.error(f"MT5 tickets not found for spread {spread_id[:8]}")
                    continue

                # Use fast CloseManager to close ALL positions with this magic number
                from utils.fast_close_all import CloseManager
                logger.info(f"Closing spread {spread_id[:8]} using fast CloseManager...")
                manager = CloseManager(magic_number=MAGIC_NUMBER, max_workers=100)
                close_result = manager.close_all()

                if not close_result['success']:
                    logger.error(f"Close FAILED!")
                    logger.error(f"  Total closed: {close_result['total_closed']}")
                    logger.error(f"  Total failed: {close_result['total_failed']}")
                    continue

                logger.info(f"[MT5 SUCCESS] All positions closed via CloseManager:")
                logger.info(f"  Total closed: {close_result['total_closed']}")
                logger.info(f"  Rounds: {close_result['rounds']}")

                # Use current snapshot prices for closing
                close_primary_price = self.current_snapshot.primary_bid if self.current_snapshot else 0.0
                close_secondary_price = self.current_snapshot.secondary_bid if self.current_snapshot else 0.0

                result = self.position_tracker.close_spread_position(
                    spread_id,
                    close_primary_price,
                    close_secondary_price
                )

                logger.info(f"[SUCCESS] P&L: ${result['total_pnl']:.2f}")

                self.account_balance += result['total_pnl']
                self.position_sizer.update_balance(self.account_balance)
                self.drawdown_monitor.update(self.account_balance)
                self.risk_checker.update_daily_pnl(result['total_pnl'])

                del self.mt5_tickets[primary_pos.position_id]
                del self.mt5_tickets[secondary_pos.position_id]

                self.rebalancer.remove_position(spread_id)

                try:
                    from pathlib import Path
                    persist_dir = Path(__file__).parent / 'data' / 'positions'
                    filepath = persist_dir / f"{spread_id}.pkl"
                    if filepath.exists():
                        filepath.unlink()
                        logger.info(f"[PERSISTENCE] Spread {spread_id[:8]} removed from disk")
                except Exception as e:
                    logger.warning(f"Failed to remove persisted position: {e}")

        except Exception as e:
            logger.error(f"Exit error: {e}")
            import traceback
            traceback.print_exc()

    def _monitor_thread(self):
        """Monitoring thread"""
        logger.info("Monitor thread started")

        while self.running:
            try:
                time.sleep(10)

                with self.lock:
                    if self.current_snapshot:
                        for position in self.position_tracker.get_all_positions():
                            if position.symbol == PRIMARY_SYMBOL:
                                self.position_tracker.update_position_price(
                                    position.position_id,
                                    self.current_snapshot.primary_bid
                                )
                            elif position.symbol == SECONDARY_SYMBOL:
                                self.position_tracker.update_position_price(
                                    position.position_id,
                                    self.current_snapshot.secondary_bid
                                )

                    pnl_data = self.position_tracker.get_total_pnl()

                    dd_metrics = self.drawdown_monitor.get_metrics()

                    within_limits, msg = self.risk_checker.check_risk_limit()

                    if not within_limits:
                        logger.critical(f"RISK LIMIT BREACH: {msg}")

                    logger.info(f"[STATUS] Balance: ${self.account_balance:,.2f} | "
                                f"Open Positions: {pnl_data['open_positions']} | "
                                f"Unrealized P&L: ${pnl_data['unrealized_pnl']:,.2f} | "
                                f"Drawdown: {dd_metrics.current_drawdown_pct:.2%}")

            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(5)

    def get_status(self) -> dict:
        """Get current system status"""
        with self.lock:
            pnl_data = self.position_tracker.get_total_pnl()
            dd_metrics = self.drawdown_monitor.get_metrics()

            return {
                'running': self.running,
                'account_balance': self.account_balance,
                'open_positions': pnl_data['open_positions'],
                'unrealized_pnl': pnl_data['unrealized_pnl'],
                'realized_pnl': pnl_data['realized_pnl'],
                'total_pnl': pnl_data['total_pnl'],
                'current_drawdown': dd_metrics.current_drawdown_pct,
                'max_drawdown': dd_metrics.max_drawdown_pct,
                'current_signal': self.current_signal.signal_type.value if self.current_signal else 'NONE',
                'current_zscore': self.current_snapshot.zscore if self.current_snapshot else 0.0,
                'last_update': self.last_update_time.isoformat() if self.last_update_time else None
            }


def main():
    """Main entry point"""
    setup_logging()

    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║     NAS100/SP500 PAIR TRADING SYSTEM - Multi-Threaded v1.0      ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)

    logger.info("="*70)
    logger.info("SYSTEM STARTING")
    logger.info("="*70)

    system = TradingSystem(
        account_balance=100000,
        update_interval=60,
        max_positions=10,
        volume_multiplier=10
    )

    try:
        system.start()

        logger.info("="*70)
        logger.info("SYSTEM RUNNING - Press Ctrl+C to stop")
        logger.info("="*70)

        while True:
            time.sleep(60)

            status = system.get_status()

            print("\n" + "="*70)
            print(f"STATUS - {datetime.now().strftime('%H:%M:%S')}")
            print("="*70)
            print(f"Balance: ${status['account_balance']:,.2f}")
            print(f"Positions: {status['open_positions']}")
            print(f"P&L: ${status['total_pnl']:,.2f}")
            print(f"Drawdown: {status['current_drawdown']:.2%}")
            print(f"Signal: {status['current_signal']}")
            print("="*70)

    except KeyboardInterrupt:
        logger.info("\nShutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        system.stop()
        logger.info("System shutdown complete")


if __name__ == "__main__":
    main()
