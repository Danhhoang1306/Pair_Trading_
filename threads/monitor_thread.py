"""
MonitorThread - Extracted from main_cli.py
"""
import time
import queue
import logging
from datetime import datetime
from .base_thread import BaseThread

logger = logging.getLogger(__name__)


class MonitorThread(BaseThread):
    """Thread worker for monitor thread"""
    
    def __init__(self, system):
        super().__init__("MonitorThread", system)
    
    def run(self):
        """Monitoring thread - syncs positions with MT5 real P&L"""
        logger.info("Monitor thread started")
        
        while self.system.running:
            try:
                time.sleep(10)
                
                # ========== CHECK AUTO-UNLOCK ==========
                # Check if should unlock (new session started)
                try:
                    self.system.trading_lock_manager._check_auto_unlock()  # Use system's trading_lock_manager
                except Exception as e:
                    logger.error(f"Auto-unlock check error: {e}")
                
                with self.system.lock:  # Use system's lock
                    # ========== SYNC POSITIONS WITH MT5 REAL P&L ==========
                    try:
                        from core.mt5_manager import get_mt5
                        mt5 = get_mt5()
                        mt5_positions = mt5.positions_get()
                        
                        if mt5_positions:
                            # Update each position with REAL MT5 P&L
                            for mt5_pos in mt5_positions:
                                ticket = mt5_pos.ticket
                                
                                # Find our internal position
                                if ticket in self.system.mt5_tickets:
                                    spread_id, leg = self.system.mt5_tickets[ticket]
                                    
                                    # Get our position
                                    positions = self.system.position_tracker.get_all_positions()
                                    for pos in positions:
                                        if pos.position_id == spread_id + f"_{leg}":
                                            # Update with REAL MT5 P&L (includes spread, commission, swap!)
                                            old_pnl = pos.unrealized_pnl
                                            pos.unrealized_pnl = mt5_pos.profit  # REAL P&L from MT5!
                                            
                                            # Update price too
                                            pos.current_price = mt5_pos.price_current
                                            
                                            # Log if significant difference
                                            pnl_diff = abs(pos.unrealized_pnl - old_pnl)
                                            if pnl_diff > 10:  # $10 difference
                                                logger.debug(f"Position {leg} P&L updated: "
                                                           f"Internal=${old_pnl:.2f}, "
                                                           f"MT5=${mt5_pos.profit:.2f}, "
                                                           f"Diff=${pnl_diff:.2f}")
                                            break
                            
                            # Log total real P&L
                            total_mt5_pnl = sum(p.profit for p in mt5_positions)
                            logger.debug(f"Total MT5 Unrealized P&L: ${total_mt5_pnl:,.2f}")
                        
                    except Exception as e:
                        logger.error(f"MT5 position sync error: {e}")
                    # ========== END MT5 POSITION SYNC ==========
                    
                    if self.system.last_update_time:
                        try:
                            data = self.system.data_queue.get_nowait()
                            
                            for position in self.system.position_tracker.get_all_positions():
                                if position.symbol == self.system.primary_symbol:
                                    self.system.position_tracker.update_position_price(
                                        position.position_id,
                                        data['current_primary_price']
                                    )
                                elif position.symbol == self.system.secondary_symbol:
                                    self.system.position_tracker.update_position_price(
                                        position.position_id,
                                        data['current_secondary_price']
                                    )
                        except queue.Empty:
                            pass
                    
                    pnl_data = self.system.position_tracker.get_total_pnl()
                    dd_metrics = self.system.drawdown_monitor.get_metrics()
                    
                    logger.info(f"[STATUS] Balance: ${self.system.account_balance:,.2f} | "
                               f"Positions: {pnl_data['open_positions']} | "
                               f"P&L: ${pnl_data['unrealized_pnl']:,.2f} | "
                               f"DD: {dd_metrics.current_drawdown_pct:.2%}")
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(5)
    
