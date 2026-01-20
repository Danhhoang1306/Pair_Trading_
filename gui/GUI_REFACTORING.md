# GUI Refactoring Documentation

## Tổng quan

GUI đã được tái cấu trúc từ một file monolithic (2609 dòng) thành kiến trúc modular với hai panel riêng biệt.

## Cấu trúc mới

### 1. **settings_panel.py** - Panel Cấu hình
Chứa tất cả các controls để cấu hình hệ thống:

**Chức năng:**
- ✅ Symbol selection (Primary/Secondary)
- ✅ Trading parameters (Entry/Exit thresholds, Stop Loss, Volume)
- ✅ Model parameters (Rolling Window, Update Interval, Hedge Drift)
- ✅ Risk management (Position %, Risk per trade, Daily limit, Session times)
- ✅ Advanced settings (Pyramiding, Hedge Adjustment, Magic Number)
- ✅ Save/Load settings from YAML config
- ✅ Apply settings to running system

**Signals:**
```python
settings_saved = pyqtSignal()          # Khi settings được lưu
settings_applied = pyqtSignal()        # Khi settings được apply
symbol_changed = pyqtSignal(str, str)  # Khi symbols thay đổi
```

**Public Methods:**
```python
get_symbols()              # Lấy symbol pair hiện tại
set_symbols(primary, secondary)  # Set symbol pair
save_settings()            # Lưu settings vào file
load_settings()            # Load settings từ file
apply_settings()           # Apply settings vào system
```

### 2. **display_panel.py** - Panel Hiển thị
Chứa tất cả các widget hiển thị thông tin:

**Chức năng:**
- ✅ Dashboard với live statistics
- ✅ Model metrics (Z-score, correlation, hedge ratio)
- ✅ Account & Risk Management panel
- ✅ Position overview
- ✅ P&L Attribution
- ✅ Real-time charts (ChartWidget)
- ✅ Logs display
- ✅ Start/Stop trading button

**Signals:**
```python
start_stop_clicked = pyqtSignal()  # Khi button start/stop được click
```

**Public Methods:**
```python
add_log(message)                              # Thêm log message
update_chart(snapshot)                        # Update chart
update_live_stats(z_score, correlation, ...)  # Update live stats
update_model_metrics(metrics)                 # Update metrics
update_account_info(balance, equity, ...)     # Update account
update_position_overview(overview)            # Update positions
update_risk_manager(risk_data)                # Update risk
update_pnl_attribution(attribution)           # Update P&L
update_total_pnl(pnl)                        # Update total P&L
update_status(status, color)                  # Update status
```

### 3. **main_window_compact.py** - Main Window (Compact)
File main window mới, gọn gàng hơn:

**Giảm từ 2609 dòng xuống ~500 dòng!**

**Chức năng:**
- ✅ Khởi tạo và quản lý 2 panels
- ✅ Quản lý TradingSystemThread
- ✅ Xử lý signals giữa các components
- ✅ Update display theo real-time
- ✅ Start/Stop trading logic
- ✅ MT5 integration

**Architecture:**
```
PairTradingGUI (QMainWindow)
├── QTabWidget
│   ├── DisplayPanel (Dashboard + Charts + Logs)
│   ├── SettingsPanel (Configuration)
│   └── PairDiscoveryTab (Pair Discovery)
├── TradingSystemThread (Background trading)
├── StopThread (Non-blocking stop)
└── Update Timer (1s interval)
```

## Migration Path

### Từ main_window_integrated.py sang main_window_compact.py

**File cũ (backup):**
```
gui/main_window_integrated.py.backup  # File gốc (2609 dòng)
```

**Files mới:**
```
gui/settings_panel.py         # Panel cấu hình (~450 dòng)
gui/display_panel.py          # Panel hiển thị (~650 dòng)
gui/main_window_compact.py    # Main window (~500 dòng)
```

**Tổng cộng: ~1600 dòng (giảm 40%)**

### Để sử dụng phiên bản mới:

File `launch_gui.py` đã được cập nhật:
```python
from gui.main_window_compact import main  # ← Sử dụng version mới
```

### Để quay lại phiên bản cũ:

Thay đổi trong `launch_gui.py`:
```python
from gui.main_window_integrated import main  # ← Version cũ
```

## Lợi ích của kiến trúc mới

### ✅ Separation of Concerns
- **Settings Panel**: Chỉ lo configuration và backend connection
- **Display Panel**: Chỉ lo hiển thị và visualization
- **Main Window**: Chỉ lo orchestration và coordination

### ✅ Dễ bảo trì
- Mỗi module có trách nhiệm rõ ràng
- Dễ tìm và sửa bugs
- Dễ thêm features mới

### ✅ Reusability
- Settings panel có thể dùng ở nhiều nơi
- Display components có thể tái sử dụng
- Dễ test từng module riêng

### ✅ Readability
- Code ngắn gọn, dễ đọc
- Logic rõ ràng hơn
- Dễ onboard developers mới

### ✅ Performance
- Không thay đổi performance
- Vẫn giữ nguyên update logic
- Thread management không đổi

## Testing

### Test Settings Panel:
```python
# Test save/load
settings_panel.save_settings()
settings_panel.load_settings()

# Test symbol change
settings_panel.set_symbols("BTCUSD", "ETHUSD")
primary, secondary = settings_panel.get_symbols()
```

### Test Display Panel:
```python
# Test updates
display_panel.update_live_stats(z_score=2.5, correlation=0.95, ...)
display_panel.update_account_info(100000, 101000, 1000, margin_info)
display_panel.add_log("Test message")
```

### Test Main Window:
```bash
python launch_gui.py
```

## Troubleshooting

### Nếu gặp lỗi import:
```
ModuleNotFoundError: No module named 'gui.settings_panel'
```
→ Đảm bảo bạn đang ở project root khi chạy

### Nếu GUI không hiển thị đúng:
- Kiểm tra theme đã load: `DARCULA_THEME_QSS`
- Kiểm tra signals đã connect đúng
- Check console logs

### Nếu muốn debug:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

Có thể tách thêm:
1. **Chart Panel** riêng (hiện tại đã có ChartWidget)
2. **Risk Panel** riêng nếu logic phức tạp hơn
3. **Position Table** nếu cần thêm lại
4. **Strategy Configuration** panel riêng

## Files Changed

```
✅ NEW: gui/settings_panel.py
✅ NEW: gui/display_panel.py
✅ NEW: gui/main_window_compact.py
✅ NEW: gui/GUI_REFACTORING.md
✅ MODIFIED: launch_gui.py (để sử dụng version mới)
✅ BACKUP: gui/main_window_integrated.py.backup
```

## Compatibility

- ✅ Python 3.10+
- ✅ PyQt6
- ✅ Tương thích với existing codebase
- ✅ Không breaking changes cho user
- ✅ Config files không đổi

---

**Created:** 2026-01-15
**Version:** 1.0
**Author:** Claude Code Refactoring
