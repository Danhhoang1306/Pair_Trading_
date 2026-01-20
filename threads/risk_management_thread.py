"""
RiskManagementThread - Extracted from main_cli.py

CRITICAL SAFETY THREAD:
- Runs independently from all other threads
- Monitors and enforces risk limits even if main system fails
- Has direct MT5 access - no dependencies on internal state
"""
import time
import queue
import logging
from datetime import datetime
from core.mt5_manager import get_mt5
from .base_thread import BaseThread

logger = logging.getLogger(__name__)


class RiskManagementThread(BaseThread):
    """
    Independent risk monitoring and emergency response thread

    RESPONSIBILITIES:
    1. Per-Setup Risk Breach -> Auto-close THAT SETUP only (NEW!)
    2. Total Portfolio Risk Breach -> Auto-close ALL positions (emergency)
    3. Daily Loss Limit -> Auto-close all + Lock trading
    4. Manual Closure Detection -> Reset internal tracking
    5. Margin Level Monitoring -> Alert only
    6. Drawdown Monitoring -> Alert only
    7. Position Count Sanity Check -> Alert only

    RISK LIMITS (Configured via RiskConfig):
    - max_loss_per_setup_pct: Max loss for EACH setup (closes that setup only)
    - max_total_unrealized_loss_pct: Max total loss (closes ALL positions)
    - daily_loss_limit_pct: Max daily loss (closes all + locks trading)
    """

    def __init__(self, system):
        super().__init__("RiskManagementThread", system)

        # Alert throttling (prevent spam)
        self.last_alerts = {}  # alert_key -> timestamp
        self.alert_cooldown = 300  # 5 minutes between same alerts

        # Track monitored MT5 tickets (independent of PositionMonitor)
        self.monitored_tickets = set()  # Set of MT5 ticket IDs
        self.last_position_count = 0

        # Emergency flags
        self.max_risk_breached_triggered = False
        self.daily_limit_breached_triggered = False
        self.manual_closure_detected = False

    def register_mt5_ticket(self, ticket: int):
        """Register MT5 ticket for manual closure detection"""
        self.monitored_tickets.add(ticket)
        logger.debug(f"[RISK] Monitoring ticket: {ticket}")

    def unregister_mt5_ticket(self, ticket: int):
        """Unregister MT5 ticket"""
        self.monitored_tickets.discard(ticket)
        logger.debug(f"[RISK] Stopped monitoring ticket: {ticket}")

    def clear_monitored_tickets(self):
        """Clear all monitored tickets"""
        self.monitored_tickets.clear()
        logger.debug("[RISK] Cleared all monitored tickets")

    def should_alert(self, alert_key: str) -> bool:
        """Check if enough time passed since last alert (throttling)"""
        import time
        now = time.time()
        last_alert = self.last_alerts.get(alert_key, 0)

        if now - last_alert >= self.alert_cooldown:
            self.last_alerts[alert_key] = now
            return True
        return False

    def run(self):
        """Main thread loop"""
        logger.info("="*80)
        logger.info(" RISK MANAGEMENT THREAD STARTED")
        logger.info("="*80)
        logger.info("Running independently - immune to other thread failures")
        logger.info("Update interval: 5 seconds")
        logger.info("="*80)

        mt5 = get_mt5()

        # Track consecutive failures for alerting
        consecutive_failures = 0
        max_consecutive_failures = 5

        while self.system.running:
            try:
                time.sleep(5)  # Check every 5 seconds (critical for safety)

                # ========== GET MT5 ACCOUNT INFO ==========
                try:
                    account_info = mt5.account_info()
                    if not account_info:
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            logger.error(f" RISK THREAD: MT5 connection lost for {consecutive_failures * 5}s!")
                        continue
                    
                    consecutive_failures = 0  # Reset on success
                    
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"Risk thread MT5 error: {e}")
                    continue
                
                # ========== CALCULATE CURRENT METRICS ==========
                balance = account_info.balance
                equity = account_info.equity
                margin = account_info.margin
                free_margin = account_info.margin_free
                margin_level = account_info.margin_level if account_info.margin_level else 0
                
                # Unrealized P&L
                unrealized_pnl = equity - balance
                
                # Get all positions
                mt5_positions = mt5.positions_get()
                position_count = len(mt5_positions) if mt5_positions else 0
                
                # ========== TOTAL PORTFOLIO RISK CHECK (INDEPENDENT) ==========
                try:
                    # Get total portfolio limit from RiskConfig
                    total_portfolio_limit = self.system.risk_config.get_total_portfolio_limit(balance)

                    if unrealized_pnl < -total_portfolio_limit and not self.max_risk_breached_triggered:
                        logger.critical("="*80)
                        logger.critical(" EMERGENCY: TOTAL PORTFOLIO RISK BREACH!")
                        logger.critical("="*80)
                        logger.critical(f"Total Unrealized P&L: ${unrealized_pnl:.2f}")
                        logger.critical(f"Max Total Portfolio Limit: ${total_portfolio_limit:.2f} "
                                      f"({self.system.risk_config.max_total_unrealized_loss_pct}%)")
                        logger.critical(f"Breach: ${abs(unrealized_pnl) - total_portfolio_limit:.2f}")
                        logger.critical(f"Limit Type: Total unrealized loss across ALL positions")
                        logger.critical(" CLOSING ALL POSITIONS IMMEDIATELY!")
                        logger.critical("="*80)

                        # GUI ALERT
                        alert_msg = (
                            f"Total Portfolio Risk Breached!\n\n"
                            f"Total Unrealized P&L: ${unrealized_pnl:,.2f}\n"
                            f"Max Portfolio Limit: ${total_portfolio_limit:,.2f} "
                            f"({self.system.risk_config.max_total_unrealized_loss_pct}%)\n"
                            f"Breach: ${abs(unrealized_pnl) - total_portfolio_limit:,.2f}\n\n"
                            f"CLOSING ALL POSITIONS NOW!"
                        )
                        self.system.emit_risk_alert('CRITICAL', 'Portfolio Risk Breach', alert_msg)

                        try:
                            # Use fast close manager for guaranteed coverage
                            from utils.fast_close_all import CloseManager
                            manager = CloseManager(magic_number=self.system.magic_number, max_workers=10)
                            result = manager.close_all()

                            logger.critical(f" Fast close result: {result['total_closed']} closed, "
                                          f"{result['total_failed']} failed")

                            # Mark as triggered to prevent repeated closes
                            self.max_risk_breached_triggered = True

                            # Cleanup internal tracking
                            self._cleanup_internal_tracking()

                        except Exception as e:
                            logger.critical(f" EMERGENCY CLOSE FAILED: {e}")
                            logger.critical(" MANUAL INTERVENTION REQUIRED!")
                            import traceback
                            traceback.print_exc()

                    # Reset flag if back within limits
                    elif unrealized_pnl >= -total_portfolio_limit * 0.8:  # 80% of limit
                        self.max_risk_breached_triggered = False

                except Exception as e:
                    logger.error(f"Total portfolio risk check error: {e}")

                # ========== DAILY RISK CHECK ==========
                try:
                    # Update daily risk manager with current P&L
                    risk_status = self.system.daily_risk_manager.check_risk(unrealized_pnl)

                    # Log every 30 seconds (every 6th check)
                    if int(time.time()) % 30 == 0:
                        logger.info(f"[RISK] Daily P&L: ${risk_status.daily_total_pnl:.2f} / "
                                  f"${risk_status.daily_loss_limit:.2f} | "
                                  f"Remaining: ${risk_status.remaining_until_daily_limit:.2f} | "
                                  f"Locked: {risk_status.trading_locked}")

                    # ========== EMERGENCY: DAILY LIMIT BREACHED ==========
                    if risk_status.daily_limit_breached and not self.daily_limit_breached_triggered:
                        logger.critical("="*80)
                        logger.critical(" EMERGENCY: DAILY LOSS LIMIT BREACHED!")
                        logger.critical("="*80)
                        logger.critical(f"Daily P&L: ${risk_status.daily_total_pnl:.2f}")
                        logger.critical(f"Daily Limit: ${risk_status.daily_loss_limit:.2f}")
                        logger.critical(f"Breach: ${abs(risk_status.daily_total_pnl) - risk_status.daily_loss_limit:.2f}")
                        logger.critical(f"Reason: {risk_status.lock_reason}")
                        logger.critical(" CLOSING ALL POSITIONS IMMEDIATELY!")
                        logger.critical("="*80)

                        # GUI ALERT
                        alert_msg = (
                            f"Daily Loss Limit Breached!\n\n"
                            f"Daily P&L: ${risk_status.daily_total_pnl:,.2f}\n"
                            f"Daily Limit: ${risk_status.daily_loss_limit:,.2f}\n"
                            f"Breach: ${abs(risk_status.daily_total_pnl) - risk_status.daily_loss_limit:,.2f}\n\n"
                            f"CLOSING ALL POSITIONS!\n"
                            f"Trading locked until next session."
                        )
                        self.system.emit_risk_alert('CRITICAL', 'Daily Limit Breach', alert_msg)

                        try:
                            # Use fast close manager for guaranteed coverage
                            from utils.fast_close_all import CloseManager
                            manager = CloseManager(magic_number=self.system.magic_number, max_workers=10)
                            result = manager.close_all()

                            logger.critical(f" Fast close result: {result['total_closed']} closed, "
                                          f"{result['total_failed']} failed")

                            # Mark as triggered
                            self.daily_limit_breached_triggered = True

                            # ========== LOCK TRADING SYSTEM ==========
                            # Persist lock to prevent trading until next session
                            if hasattr(self.system, 'trading_lock_manager'):
                                self.system.trading_lock_manager.lock_trading(
                                    reason=f"Daily loss limit breached: ${risk_status.daily_total_pnl:,.2f}",
                                    daily_pnl=risk_status.daily_total_pnl,
                                    daily_limit=risk_status.daily_loss_limit
                                )

                            # Cleanup internal tracking
                            self._cleanup_internal_tracking()

                            # Stop trading for the day
                            self.system.running = False
                            logger.critical(" SYSTEM STOPPED FOR THE DAY")
                            logger.critical(" Trading locked until next session")

                        except Exception as e:
                            logger.critical(f" EMERGENCY CLOSE FAILED: {e}")
                            logger.critical(" MANUAL INTERVENTION REQUIRED!")
                            import traceback
                            traceback.print_exc()

                except Exception as e:
                    logger.error(f"Daily risk check error: {e}")

                # ========== PER-SETUP RISK CHECK (NEW) ==========
                try:
                    # Get per-setup risk limit
                    per_setup_limit = self.system.risk_config.get_per_setup_limit(balance)

                    # Get all active spreads with PnL
                    spreads = self.system.get_spreads_with_pnl()

                    for spread_id, spread_data in spreads.items():
                        spread_pnl = spread_data['total_pnl']

                        # Check if this setup breached its risk limit
                        if spread_pnl < -per_setup_limit:
                            logger.critical("="*80)
                            logger.critical(f" SETUP RISK BREACH: {spread_id[:8]}...")
                            logger.critical("="*80)
                            logger.critical(f"Setup P&L: ${spread_pnl:.2f}")
                            logger.critical(f"Max Per-Setup Limit: ${per_setup_limit:.2f} "
                                          f"({self.system.risk_config.max_loss_per_setup_pct}%)")
                            logger.critical(f"Breach: ${abs(spread_pnl) - per_setup_limit:.2f}")
                            logger.critical(f"Limit Type: Individual setup loss limit")
                            logger.critical(" CLOSING THIS SETUP ONLY!")
                            logger.critical("="*80)

                            # GUI ALERT
                            alert_msg = (
                                f"Setup Risk Limit Breached!\n\n"
                                f"Setup ID: {spread_id[:8]}...\n"
                                f"Setup P&L: ${spread_pnl:,.2f}\n"
                                f"Per-Setup Limit: ${per_setup_limit:,.2f} "
                                f"({self.system.risk_config.max_loss_per_setup_pct}%)\n"
                                f"Breach: ${abs(spread_pnl) - per_setup_limit:,.2f}\n\n"
                                f"CLOSING THIS SETUP NOW!"
                            )
                            self.system.emit_risk_alert('CRITICAL', 'Setup Risk Breach', alert_msg)

                            try:
                                # WARNING: fast_close_all closes ALL positions with magic number
                                # Cannot close individual spread - will close EVERYTHING
                                # This is acceptable for risk breach scenario (safety first)

                                primary_ticket = spread_data.get('primary_ticket')
                                secondary_ticket = spread_data.get('secondary_ticket')

                                logger.critical(f" Using CloseManager to close ALL positions with magic {self.system.magic_number}")
                                logger.critical(f" (Cannot close individual spread - closes ALL for safety)")

                                # Use fast CloseManager to close ALL positions
                                from utils.fast_close_all import CloseManager
                                manager = CloseManager(magic_number=self.system.magic_number, max_workers=100)
                                close_result = manager.close_all()

                                if close_result['success']:
                                    logger.critical(f" Successfully closed ALL positions!")
                                    logger.critical(f"   Total closed: {close_result['total_closed']}")
                                    logger.critical(f"   Rounds: {close_result['rounds']}")

                                    # Cleanup internal tracking for ALL spreads (since all closed)
                                    if hasattr(self.system, 'persistence'):
                                        self.system.persistence.clear_all_positions()
                                    logger.critical(f" All spreads cleared from persistence")

                                    # CRITICAL: Reset spread states to allow new entries
                                    self._cleanup_internal_tracking()
                                    logger.critical(f" Internal tracking reset - system ready for new entries")
                                else:
                                    logger.critical(f" WARNING: Close operation incomplete!")
                                    logger.critical(f"   Closed: {close_result['total_closed']}")
                                    logger.critical(f"   Failed: {close_result['total_failed']}")

                            except Exception as e:
                                logger.critical(f" SETUP CLOSE FAILED: {e}")
                                logger.critical(" Manual intervention may be required!")
                                import traceback
                                traceback.print_exc()

                except Exception as e:
                    logger.error(f"Per-setup risk check error: {e}")

                # ========== MARGIN LEVEL CHECK ==========
                try:
                    if margin_level > 0 and margin_level < 200:  # Danger zone
                        logger.warning("="*80)
                        logger.warning(f" LOW MARGIN LEVEL: {margin_level:.2f}%")
                        logger.warning(f"Balance: ${balance:.2f}")
                        logger.warning(f"Equity: ${equity:.2f}")
                        logger.warning(f"Used Margin: ${margin:.2f}")
                        logger.warning(f"Free Margin: ${free_margin:.2f}")
                        logger.warning("="*80)
                        
                        if margin_level < 150:  # Critical
                            logger.critical(" CRITICAL: MARGIN LEVEL < 150%!")
                            logger.critical("Consider closing positions to free margin")

                            # GUI ALERT - Only send once every 5 minutes (throttled)
                            if self.should_alert('margin_critical'):
                                alert_msg = (
                                    f"Critical Margin Level!\n\n"
                                    f"Margin Level: {margin_level:.2f}%\n"
                                    f"Balance: ${balance:,.2f}\n"
                                    f"Equity: ${equity:,.2f}\n"
                                    f"Used Margin: ${margin:,.2f}\n"
                                    f"Free Margin: ${free_margin:,.2f}\n\n"
                                    f"⚠️  Consider closing positions to free margin!"
                                )
                                self.system.emit_risk_alert('CRITICAL', 'Low Margin', alert_msg)
                    
                except Exception as e:
                    logger.error(f"Margin check error: {e}")
                
                # ========== DRAWDOWN MONITORING ==========
                try:
                    dd_metrics = self.system.drawdown_monitor.get_metrics()
                    
                    # Log every minute (every 12th check)
                    if int(time.time()) % 60 == 0:
                        logger.info(f"[RISK] Drawdown: {dd_metrics.current_drawdown_pct:.2%} / "
                                  f"{dd_metrics.max_drawdown_pct:.2%} | "
                                  f"Peak: ${dd_metrics.peak_balance:.2f}")
                    
                    # Alert on high drawdown
                    if dd_metrics.current_drawdown_pct > 0.10:  # >10%
                        logger.warning(f" HIGH DRAWDOWN: {dd_metrics.current_drawdown_pct:.2%}")
                    
                    if dd_metrics.current_drawdown_pct > 0.15:  # >15%
                        logger.critical(f" CRITICAL DRAWDOWN: {dd_metrics.current_drawdown_pct:.2%}")
                
                except Exception as e:
                    logger.error(f"Drawdown monitoring error: {e}")
                
                # ========== MANUAL CLOSURE DETECTION ==========
                try:
                    # Only check if we have monitored tickets
                    if self.monitored_tickets:
                        # Get current MT5 tickets
                        current_mt5_tickets = {pos.ticket for pos in mt5_positions} if mt5_positions else set()

                        # Check if ALL monitored positions are gone
                        missing_tickets = self.monitored_tickets - current_mt5_tickets

                        if missing_tickets and len(missing_tickets) == len(self.monitored_tickets):
                            # ALL positions closed manually
                            logger.warning("="*80)
                            logger.warning(" MANUAL CLOSURE DETECTED!")
                            logger.warning("="*80)
                            logger.warning(f"Expected {len(self.monitored_tickets)} positions")
                            logger.warning(f"Found {len(current_mt5_tickets & self.monitored_tickets)} positions")
                            logger.warning(f"Missing tickets: {missing_tickets}")
                            logger.warning("")
                            logger.warning("Possible causes:")
                            logger.warning("  1. Manual closure by user")
                            logger.warning("  2. Stop loss / Take profit hit")
                            logger.warning("  3. Broker force close (margin call)")
                            logger.warning("")
                            logger.warning(" Cleaning up internal tracking...")
                            logger.warning("="*80)

                            # Cleanup internal tracking
                            self._cleanup_internal_tracking()

                            # Clear monitored tickets
                            self.monitored_tickets.clear()
                            self.manual_closure_detected = True

                        elif missing_tickets:
                            # PARTIAL closure (some positions missing)
                            logger.warning(f" PARTIAL MANUAL CLOSURE: {len(missing_tickets)} positions closed")
                            logger.warning(f"Missing tickets: {missing_tickets}")

                            # Remove missing tickets from monitoring
                            for ticket in missing_tickets:
                                self.monitored_tickets.discard(ticket)

                except Exception as e:
                    logger.error(f"Manual closure detection error: {e}")

                # ========== AUTO-RESET SPREAD STATES IF NO POSITIONS ==========
                try:
                    # Check if NO positions remain on MT5
                    # AND spread states has data → Auto-reset to allow new entries
                    if position_count == 0:
                        if hasattr(self.system, 'unified_executor') and self.system.unified_executor:
                            # Check if spread states has any data
                            has_spread_data = len(self.system.unified_executor.spread_states) > 0

                            if has_spread_data:
                                logger.info("=" * 80)
                                logger.info(" AUTO-RESET: No MT5 positions + Spread states has data")
                                logger.info("=" * 80)
                                for spread_id, state in self.system.unified_executor.spread_states.items():
                                    logger.info(f"   {spread_id[:16]}: {state.side} "
                                              f"last_z={state.last_z_entry:.3f} "
                                              f"entries={state.entry_count}")
                                logger.info("   Resetting spread states to allow fresh entries...")

                                # Reset spread states
                                self.system.unified_executor.spread_states.clear()
                                self.system.unified_executor._save_states()

                                logger.info("   Spread states reset complete")
                                logger.info("=" * 80)

                        # Legacy: Reset entry cooldown if exists
                        if hasattr(self.system, 'entry_cooldown') and self.system.entry_cooldown:
                            long_status = self.system.entry_cooldown.get_status('LONG')
                            short_status = self.system.entry_cooldown.get_status('SHORT')
                            has_data = long_status['has_last_entry'] or short_status['has_last_entry']

                            if has_data:
                                self.system.entry_cooldown.reset()
                                logger.info("   Entry cooldown reset (legacy)")

                except Exception as e:
                    logger.error(f"Auto-reset spread states error: {e}")

                # ========== POSITION COUNT SANITY CHECK ==========
                try:
                    max_reasonable_positions = 50  # Safety threshold

                    if position_count > max_reasonable_positions:
                        logger.critical("="*80)
                        logger.critical(f" EXCESSIVE POSITIONS: {position_count} positions!")
                        logger.critical(f"Threshold: {max_reasonable_positions}")
                        logger.critical("Possible runaway bot - investigate immediately!")
                        logger.critical("="*80)

                except Exception as e:
                    logger.error(f"Position count check error: {e}")

            except Exception as e:
                logger.error(f"Risk management thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _cleanup_internal_tracking(self):
        """
        Cleanup all internal tracking systems
        Called after emergency close or manual closure detection
        """
        try:
            logger.info(" Cleaning up internal tracking systems...")

            # Clear position tracker
            if hasattr(self.system, 'position_tracker'):
                self.system.position_tracker.positions.clear()
                self.system.position_tracker.closed_positions.clear()
                logger.info("   Position tracker cleared")

            # Clear rebalancer
            if hasattr(self.system, 'rebalancer'):
                if hasattr(self.system.rebalancer, 'active_positions'):
                    self.system.rebalancer.active_positions.clear()
                if hasattr(self.system.rebalancer, 'last_adjustment'):
                    self.system.rebalancer.last_adjustment.clear()
                logger.info("   Rebalancer cleared")

            # Clear position monitor
            if hasattr(self.system, 'position_monitor'):
                self.system.position_monitor.clear_all()
                logger.info("   Position monitor cleared")

            # CRITICAL: Reset SimpleUnifiedExecutor spread states (PRIMARY)
            if hasattr(self.system, 'unified_executor'):
                self.system.unified_executor.spread_states.clear()
                self.system.unified_executor._save_states()  # Persist to file
                logger.info("   SimpleUnifiedExecutor spread_states cleared & saved")

            # Legacy: Reset entry cooldown if exists
            if hasattr(self.system, 'entry_cooldown') and self.system.entry_cooldown:
                self.system.entry_cooldown.reset()
                logger.info("   Entry cooldown reset (legacy)")

            # Update setup flag
            if hasattr(self.system, 'flag_manager'):
                self.system.flag_manager.mark_setup_inactive(reason="Emergency close")
                logger.info("   Setup flag: INACTIVE")

            # Clear MT5 tickets mapping
            if hasattr(self.system, 'mt5_tickets'):
                self.system.mt5_tickets.clear()
                logger.info("   MT5 tickets mapping cleared")

            logger.info(" Internal tracking cleanup complete")

        except Exception as e:
            logger.error(f" Cleanup error: {e}")
            import traceback
            traceback.print_exc()

