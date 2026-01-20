"""
DataThread - Extracted from main_cli.py
"""
import time
import queue
import logging
from datetime import datetime
from core.mt5_manager import get_mt5
from .base_thread import BaseThread

logger = logging.getLogger(__name__)


class DataThread(BaseThread):
    """Thread worker for data thread"""
    
    def __init__(self, system):
        super().__init__("DataThread", system)
    
    def run(self):
        """Data fetching thread - TRUE ROLLING WINDOW"""
        logger.info("Data thread started")
        
        # Bootstrap rolling window ONCE at startup
        logger.info("Bootstrapping rolling window with historical data...")
        try:
            self.system.market_data.bootstrap_window(days=30)
            logger.info("Rolling window ready - starting real-time updates")
            
            # Get IMMEDIATE first snapshot (don't wait for update_interval)
            logger.info("Fetching initial snapshot...")
            initial_snapshot = self.system.market_data.get_realtime_snapshot()
            
            if initial_snapshot:
                self.system.current_snapshot = initial_snapshot
                logger.info(f"Initial snapshot ready - Z-Score: {initial_snapshot.zscore:.3f}")
            else:
                logger.error("Failed to get initial snapshot!")
        
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            import traceback
            traceback.print_exc()
            # Continue anyway, maybe MT5 will connect later
        
        while self.system.running:
            try:
                logger.debug("DataThread: Starting iteration...")
                
                # Get real-time snapshot
                # This updates current H1 bar's close and recalculates stats
                logger.debug("DataThread: Getting snapshot...")
                snapshot = self.system.market_data.get_realtime_snapshot()
                
                if snapshot is None:
                    logger.error("Failed to get market snapshot")
                    time.sleep(10)
                    continue
                
                logger.debug(f"DataThread: Got snapshot Z={snapshot.zscore:.3f}")
                
                # Get volatility
                primary_vol, secondary_vol = self.system.market_data.get_volatility()
                
                # Package data for other threads
                data = {
                    'timestamp': snapshot.timestamp,
                    'snapshot': snapshot,
                    'current_primary_price': snapshot.primary_bid,
                    'current_secondary_price': snapshot.secondary_bid,
                    'current_zscore': snapshot.zscore,
                    'primary_vol': primary_vol,
                    'secondary_vol': secondary_vol
                }
                
                # Push to queue
                try:
                    self.system.data_queue.put(data, block=False)
                    logger.info(f"✅ DataThread: Pushed data to queue (Z={snapshot.zscore:.3f})")
                    logger.debug(f"Rolling update: {snapshot}")
                    logger.debug(f"  Mean: {snapshot.spread_mean:.2f}, Std: {snapshot.spread_std:.2f}")
                except queue.Full:
                    logger.warning("Data queue full")
                
                self.system.last_update_time = datetime.now()
                self.system.current_snapshot = snapshot
                
                # ========== CRITICAL: SYNC WITH MT5 REAL BALANCE ==========
                try:
                    mt5 = get_mt5()
                    mt5_info = mt5.account_info()
                    
                    if mt5_info:
                        # Get REAL balance and equity from MT5
                        mt5_balance = mt5_info.balance
                        mt5_equity = mt5_info.equity
                        mt5_profit = mt5_info.profit  # Current unrealized P&L
                        
                        # Calculate drift between internal and MT5
                        balance_drift = abs(self.system.account_balance - mt5_balance)
                        
                        if balance_drift > 100:  # $100 drift warning
                            logger.warning(f"  Balance drift detected: "
                                         f"Internal=${self.system.account_balance:,.2f}, "
                                         f"MT5=${mt5_balance:,.2f}, "
                                         f"Drift=${balance_drift:,.2f}")
                        
                        # Update drawdown monitor with REAL MT5 equity
                        # This is CRITICAL for accurate risk management!
                        self.system.drawdown_monitor.update(mt5_equity)
                        
                        # Update risk checker with real balance
                        if hasattr(self, 'position_sizer'):
                            self.system.position_sizer.update_balance(mt5_balance)
                        
                        # Update executor balances
                        if hasattr(self, 'entry_executor'):
                            self.system.entry_executor.update_balance(mt5_balance)
                        if hasattr(self, 'exit_executor'):
                            self.system.exit_executor.update_balance(mt5_balance)
                        
                        # Log MT5 real data (INFO level for visibility)
                        logger.info(f"[MT5 SYNC] Balance=${mt5_balance:,.2f}, "
                                   f"Equity=${mt5_equity:,.2f}, "
                                   f"Unrealized P&L=${mt5_profit:,.2f}")
                        
                        # ========== RISK MONITORING (INFO ONLY) ==========
                        # NOTE: Actual risk management is handled by RiskManagementThread
                        # DataThread only logs for visibility
                        risk_status = self.system.daily_risk_manager.check_risk(mt5_profit)

                        logger.info(f"[RISK CHECK] "
                                  f"Open P&L: ${risk_status.unrealized_pnl:,.2f} / "
                                  f"${risk_status.max_risk_limit:,.2f} | "
                                  f"Daily P&L: ${risk_status.daily_total_pnl:,.2f} / "
                                  f"-${risk_status.daily_loss_limit:,.2f} | "
                                  f"Remaining: ${risk_status.remaining_until_daily_limit:,.2f}")

                        # REMOVED: Risk breach handling
                        # Risk management is now handled by RiskManagementThread:
                        # - Max risk breach → auto-close by RiskManagementThread
                        # - Daily loss limit → auto-close + lock by RiskManagementThread
                        # This eliminates duplicate logic and race conditions

                        # Keep drawdown monitor for compatibility
                        dd_metrics = self.system.drawdown_monitor.get_metrics()
                        logger.debug(f"[DD CHECK] Current: {dd_metrics.current_drawdown_pct:.4%}, "
                                   f"Limit: {self.system.max_drawdown_limit:.4%}")
                        # ========== END RISK MONITORING ==========
                    else:
                        logger.warning("Failed to get MT5 account info")
                        
                except Exception as e:
                    logger.error(f"MT5 sync error: {e}")
                # ========== END MT5 SYNC ==========
                
                # Sleep
                time.sleep(self.system.update_interval)
                
            except Exception as e:
                logger.error(f"Data thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)
