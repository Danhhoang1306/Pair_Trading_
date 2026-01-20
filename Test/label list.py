import csv
from pathlib import Path

# Phân tích từ code main_window_integrated.py
labels_data = [
    # Format: [Section, Label Text, Variable Name, Display Status, Location/Panel]

    # ===== CONTROL PANEL =====
    ["Control Panel", "Primary Symbol:", "primary_input", "YES", "Symbol Selection - Input field"],
    ["Control Panel", "Secondary Symbol:", "secondary_input", "YES", "Symbol Selection - Input field"],
    ["Control Panel", "Start/Stop Button", "start_stop_btn", "YES", "Symbol Selection - Button"],

    # ===== LIVE STATISTICS =====
    ["Live Statistics", "Z-Score:", "zscore_label", "YES", "Stats Group - Live data"],
    ["Live Statistics", "Correlation:", "correlation_label", "YES", "Stats Group - Live data"],
    ["Live Statistics", "Hedge Ratio:", "hedge_ratio_label", "YES", "Stats Group - Live data"],
    ["Live Statistics", "Spread:", "spread_label", "YES", "Stats Group - Live data"],
    ["Live Statistics", "Total P&L:", "pnl_label", "YES", "Stats Group - Live data"],
    ["Live Statistics", "Signal:", "signal_label", "YES", "Stats Group - Live data"],

    # ===== MODEL METRICS PANEL =====
    ["Model Metrics", "Entry Threshold:", "entry_threshold_display", "YES", "Model Metrics - Row 0"],
    ["Model Metrics", "Spread Mean:", "mean_label", "YES", "Model Metrics - Row 0"],
    ["Model Metrics", "Mean Drift:", "mean_drift_label", "YES", "Model Metrics - Row 0"],
    ["Model Metrics", "Exit Threshold:", "exit_threshold_display", "YES", "Model Metrics - Row 1"],
    ["Model Metrics", "Spread Std:", "std_label", "YES", "Model Metrics - Row 1"],
    ["Model Metrics", "Window Size:", "window_size_display", "YES", "Model Metrics - Row 1"],
    ["Model Metrics", "Max Z-Score:", "max_zscore_label", "YES", "Model Metrics - Row 2"],
    ["Model Metrics", "Max Mean:", "max_mean_label", "YES", "Model Metrics - Row 2"],
    ["Model Metrics", "Last Update:", "last_update_label", "YES", "Model Metrics - Row 2"],
    ["Model Metrics", "Min Z-Score:", "min_zscore_label", "YES", "Model Metrics - Row 3"],
    ["Model Metrics", "Min Mean:", "min_mean_label", "YES", "Model Metrics - Row 3"],
    ["Model Metrics", "Status:", "status_indicator", "YES", "Model Metrics - Row 3"],

    # ===== ACCOUNT STATUS (Unified Panel) =====
    ["Account Status", "Balance:", "mt5_balance_label", "YES", "Unified Panel - Row 1"],
    ["Account Status", "Equity:", "mt5_equity_label", "YES", "Unified Panel - Row 1"],
    ["Account Status", "Unrealized P&L:", "mt5_profit_label", "YES", "Unified Panel - Row 1"],
    ["Account Status", "Used Margin:", "mt5_margin_label", "YES", "Unified Panel - Row 2"],
    ["Account Status", "Free Margin:", "mt5_margin_free_label", "YES", "Unified Panel - Row 2"],
    ["Account Status", "Margin Level:", "mt5_margin_level_label", "YES", "Unified Panel - Row 2"],

    # ===== POSITION OVERVIEW (Unified Panel) =====
    ["Position Overview", "Open Spread:", "mt5_positions_label", "YES", "Unified Panel - Row 4"],
    ["Position Overview", "Open/Close:", "positions_count_label", "YES", "Unified Panel - Row 4"],
    ["Position Overview", "Total Lots:", "mt5_total_lots_label", "YES", "Unified Panel - Row 4"],
    ["Position Overview", "Hedge Quality:", "mt5_hedge_quality_label", "YES", "Unified Panel - Row 5"],
    ["Position Overview", "Imbalance:", "mt5_hedge_imbalance_label", "YES", "Unified Panel - Row 5"],
    ["Position Overview", "Value:", "mt5_hedge_imbalance_value_label", "YES", "Unified Panel - Row 5"],

    # ===== RISK MANAGER (Unified Panel) =====
    ["Risk Manager", "Risk % (Setup):", "setup_risk_pct_label", "YES", "Unified Panel - Row 8"],
    ["Risk Manager", "Risk % (Daily):", "risk_daily_pct_label", "YES", "Unified Panel - Row 8"],
    ["Risk Manager", "Trading Status:", "risk_trading_status_label", "YES", "Unified Panel - Row 8"],
    ["Risk Manager", "Risk $ (Setup):", "setup_risk_label", "YES", "Unified Panel - Row 9"],
    ["Risk Manager", "Risk $ (Daily):", "risk_daily_limit_label", "YES", "Unified Panel - Row 9"],
    ["Risk Manager", "Block Time:", "risk_lock_until_label", "YES", "Unified Panel - Row 9"],
    ["Risk Manager", "Unrealized:", "risk_unrealized_pnl_label", "YES", "Unified Panel - Row 10"],
    ["Risk Manager", "Total PnL:", "risk_daily_pnl_label", "YES", "Unified Panel - Row 10"],
    ["Risk Manager", "Unlock Time:", "risk_unlock_time_label", "YES", "Unified Panel - Row 10"],

    # ===== HIDDEN LABELS (Backward Compatibility) =====
    ["Hidden/Legacy", "Starting Balance:", "risk_starting_balance_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Remaining:", "risk_remaining_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Max Open Limit:", "risk_max_open_limit_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Current Open Loss:", "risk_current_open_loss_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Max Open Status:", "risk_max_open_status_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Setup ID:", "setup_id_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Setup Entry PnL:", "setup_entry_pnl_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Total Setups:", "total_setups_label", "NO (Hidden)", "Backward compatibility"],
    ["Hidden/Legacy", "Primary Lots:", "mt5_primary_lots_label", "NO (Hidden)", "Data in mt5_total_lots_label"],
    ["Hidden/Legacy", "Secondary Lots:", "mt5_secondary_lots_label", "NO (Hidden)", "Data in mt5_total_lots_label"],
    ["Hidden/Legacy", "Hedge Imbalance %:", "mt5_hedge_imbalance_pct_label", "NO (Hidden)", "Data in hedge quality"],
    ["Hidden/Legacy", "Stop Loss:", "mt5_stop_loss_label", "NO (Hidden)", "Not needed in unified view"],
    ["Hidden/Legacy", "Max Risk:", "mt5_max_risk_label", "NO (Hidden)", "Not needed in unified view"],
    ["Hidden/Legacy", "Risk Amount:", "mt5_risk_amount_label", "NO (Hidden)", "Shown per-setup"],
    ["Hidden/Legacy", "Distance to SL:", "mt5_distance_to_sl_label", "NO (Hidden)", "Not needed"],
    ["Hidden/Legacy", "Open PnL:", "risk_open_pnl_label", "NO (Hidden)", "Shown in unrealized P&L"],
    ["Hidden/Legacy", "Open Status:", "risk_open_status_label", "NO (Hidden)", "Shown in hedge quality"],

    # ===== P&L ATTRIBUTION PANEL =====
    ["P&L Attribution", "Spread P&L:", "attr_spread_pnl_label", "YES", "Attribution Panel - Row 0"],
    ["P&L Attribution", "Spread %:", "attr_spread_pct_label", "YES", "Attribution Panel - Row 0"],
    ["P&L Attribution", "Mean Drift P&L:", "attr_mean_pnl_label", "YES", "Attribution Panel - Row 1"],
    ["P&L Attribution", "Mean Drift %:", "attr_mean_pct_label", "YES", "Attribution Panel - Row 1"],
    ["P&L Attribution", "Directional P&L:", "attr_directional_pnl_label", "YES", "Attribution Panel - Row 2"],
    ["P&L Attribution", "Directional %:", "attr_directional_pct_label", "YES", "Attribution Panel - Row 2"],
    ["P&L Attribution", "Hedge Imbalance:", "attr_hedge_pnl_label", "YES", "Attribution Panel - Row 3"],
    ["P&L Attribution", "Hedge %:", "attr_hedge_pct_label", "YES", "Attribution Panel - Row 3"],
    ["P&L Attribution", "Transaction Costs:", "attr_costs_label", "YES", "Attribution Panel - Row 0 (right)"],
    ["P&L Attribution", "Costs %:", "attr_costs_pct_label", "YES", "Attribution Panel - Row 0 (right)"],
    ["P&L Attribution", "Slippage:", "attr_slippage_label", "YES", "Attribution Panel - Row 1 (right)"],
    ["P&L Attribution", "Slippage %:", "attr_slippage_pct_label", "YES", "Attribution Panel - Row 1 (right)"],
    ["P&L Attribution", "Rebalance Alpha:", "attr_rebalance_label", "YES", "Attribution Panel - Row 2 (right)"],
    ["P&L Attribution", "Rebalance %:", "attr_rebalance_pct_label", "YES", "Attribution Panel - Row 2 (right)"],
    ["P&L Attribution", "Hedge Quality:", "attr_hedge_quality_label", "YES", "Attribution Panel - Row 5"],
    ["P&L Attribution", "Strategy Purity:", "attr_purity_label", "YES", "Attribution Panel - Row 5"],
    ["P&L Attribution", "Classification:", "attr_class_label", "YES", "Attribution Panel - Row 5"],

    # ===== SETTINGS TAB =====
    ["Settings - Trading", "Entry Z-Score:", "entry_zscore_spin", "YES", "Settings Tab - Trading Parameters"],
    ["Settings - Trading", "Exit Z-Score:", "exit_zscore_spin", "YES", "Settings Tab - Trading Parameters"],
    ["Settings - Trading", "Stop Loss Z-Score:", "stop_zscore_spin", "YES", "Settings Tab - Trading Parameters"],
    ["Settings - Trading", "Max Positions:", "max_positions_spin", "YES", "Settings Tab - Trading Parameters"],
    ["Settings - Trading", "Volume Multiplier:", "volume_mult_spin", "YES", "Settings Tab - Trading Parameters"],

    ["Settings - Model", "Rolling Window:", "window_spin", "YES", "Settings Tab - Model Parameters"],
    ["Settings - Model", "Update Interval (s):", "interval_spin", "YES", "Settings Tab - Model Parameters"],
    ["Settings - Model", "Hedge Drift Threshold:", "hedge_drift_spin", "YES", "Settings Tab - Model Parameters"],
    ["Settings - Model", "Enable Pyramiding", "pyramiding_check", "YES", "Settings Tab - Model Parameters"],
    ["Settings - Model", "Enable Hedge Adjustment", "hedge_adjust_check", "YES", "Settings Tab - Model Parameters"],
    ["Settings - Model", "Enable Entry Cooldown", "entry_cooldown_check", "YES", "Settings Tab - Model Parameters"],
    ["Settings - Model", "Enable Manual Sync", "manual_sync_check", "YES", "Settings Tab - Model Parameters"],

    ["Settings - Risk", "Max Position %:", "max_pos_pct_spin", "YES", "Settings Tab - Risk Management"],
    ["Settings - Risk", "Risk Per Setup:", "max_risk_pct_spin", "YES", "Settings Tab - Risk Management"],
    ["Settings - Risk", "Daily Risk Limit:", "daily_loss_spin", "YES", "Settings Tab - Risk Management"],
    ["Settings - Risk", "Session Start Time:", "session_start_input", "YES", "Settings Tab - Risk Management"],
    ["Settings - Risk", "Session End Time:", "session_end_input", "YES", "Settings Tab - Risk Management"],

    ["Settings - Advanced", "Scale Interval:", "scale_interval_spin", "YES", "Settings Tab - Advanced Settings"],
    ["Settings - Advanced", "Initial Fraction:", "initial_fraction_spin", "YES", "Settings Tab - Advanced Settings"],
    ["Settings - Advanced", "Min Adjust Interval:", "min_adjust_interval_spin", "YES",
     "Settings Tab - Advanced Settings"],
    ["Settings - Advanced", "Magic Number:", "magic_number_spin", "YES", "Settings Tab - Advanced Settings"],
    ["Settings - Advanced", "Z-Score History:", "zscore_history_spin", "YES", "Settings Tab - Advanced Settings"],

    # ===== OTHER UI ELEMENTS =====
    ["UI Elements", "Log Display", "log_display", "YES", "Logs Tab - Text display"],
    ["UI Elements", "Status Bar", "statusBar", "YES", "Main Window - Bottom status"],
    ["UI Elements", "Chart Widget", "chart_widget", "YES", "Charts Tab - Real-time charts"],
    ["UI Elements", "Discovery Tab", "discovery_tab", "YES", "Pair Discovery Tab"],
]

# Tạo file CSV
output_file = "gui_labels_analysis.csv"

with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)

    # Header
    writer.writerow([
        "Section/Panel",
        "Label Text",
        "Variable Name",
        "Display Status",
        "Location/Notes"
    ])

    # Data rows
    writer.writerows(labels_data)

print(f"✅ Created {output_file}")
print(f"📊 Total labels analyzed: {len(labels_data)}")
print(f"\nBreakdown:")
print(f"  - Visible labels: {sum(1 for row in labels_data if 'YES' in row[3])}")
print(f"  - Hidden labels: {sum(1 for row in labels_data if 'NO' in row[3])}")

# Thống kê theo section
from collections import Counter

sections = Counter(row[0] for row in labels_data)
print(f"\nLabels by section:")
for section, count in sections.most_common():
    print(f"  - {section}: {count}")