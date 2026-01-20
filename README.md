# Pair Trading Pro

Hệ thống giao dịch cặp (Pair Trading) tự động với MetaTrader 5 - Chiến lược Statistical Arbitrage chuyên nghiệp.

## Tổng quan

Pair Trading Pro là một hệ thống giao dịch tự động hoàn chỉnh, triển khai chiến lược pair trading (statistical arbitrage) trên nền tảng MetaTrader 5. Hệ thống hỗ trợ giao dịch nhiều cặp tài sản đồng thời (Crypto, Indices, Forex) với quản lý rủi ro 3 lớp và giao diện đồ họa trực quan.

### Tính năng chính

- **Quản lý rủi ro 3 lớp**
  - Per-Setup Loss Limit: Giới hạn lỗ cho từng setup riêng lẻ
  - Total Portfolio Loss Limit: Giới hạn tổng lỗ chưa thực hiện trên toàn bộ danh mục
  - Daily Loss Limit: Giới hạn tổng lỗ mỗi ngày (đã thực hiện + chưa thực hiện)

- **Trading Lock Manager**: Tự động khóa giao dịch khi vi phạm giới hạn rủi ro

- **State Persistence**: Vị thế và trạng thái được lưu trữ, tồn tại qua khởi động lại hệ thống

- **Hybrid Rebalancer**: Logic kết hợp pyramiding và điều chỉnh hedge ratio

- **GUI Dashboard**: Biểu đồ thời gian thực, giám sát rủi ro và điều khiển hệ thống

- **Backtest Engine**: Kiểm tra lịch sử với dữ liệu MT5

- **Multi-pair Support**: Giao dịch đồng thời nhiều cặp (Crypto, Indices, Forex)

## Kiến trúc hệ thống

```
pair_trading_pro/
├── core/                   # Module lõi
│   ├── data_manager.py           # Quản lý dữ liệu giá, tính toán chỉ báo
│   ├── mt5_connector.py          # Kết nối và giao tiếp với MT5
│   ├── mt5_manager.py            # Quản lý giao dịch MT5
│   ├── mt5_trade_executor.py    # Thực thi lệnh
│   ├── position_monitor.py       # Giám sát vị thế
│   └── position_persistence.py   # Lưu trữ trạng thái
├── strategy/               # Chiến lược giao dịch
│   ├── signal_generator.py       # Tạo tín hiệu giao dịch (Z-score)
│   ├── hybrid_rebalancer.py      # Pyramiding & hedge adjustment
│   ├── entry_cooldown.py         # Cooldown để tránh entry trùng lặp
│   ├── position_tracker.py       # Theo dõi vị thế
│   └── order_manager.py          # Quản lý lệnh
├── risk/                   # Quản lý rủi ro
│   ├── risk_manager.py           # 3-layer risk management
│   └── trading_lock_manager.py   # Khóa giao dịch tự động
├── executors/              # Các executor
│   ├── entry_executor.py         # Thực thi entry
│   ├── exit_executor.py          # Thực thi exit
│   ├── pyramiding_executor.py    # Thực thi pyramiding
│   └── volume_rebalancer.py      # Cân bằng khối lượng
├── gui/                    # Giao diện đồ họa (PyQt6)
│   ├── dashboard.py              # Dashboard chính
│   ├── charts.py                 # Biểu đồ thời gian thực
│   └── controls.py               # Các control widget
├── handlers/               # Event handlers
├── recovery/               # Recovery logic
├── threads/                # Multi-threading
├── utils/                  # Utilities
├── models/                 # Data models
├── config/                 # Configuration files (YAML)
├── analysis/               # Analysis tools
├── analytics/              # Analytics & reporting
└── tests/                  # Unit tests

# Entry points
├── launch_gui.py           # Khởi chạy GUI
├── main_cli.py             # CLI cho crypto pairs
└── main_indices_cli.py     # CLI cho indices pairs
```

## Cài đặt

### Yêu cầu hệ thống

- Windows 10/11 (do MT5 chỉ hỗ trợ Windows)
- Python 3.8 trở lên
- MetaTrader 5 đã cài đặt và đăng nhập
- RAM: Tối thiểu 4GB, khuyến nghị 8GB
- Kết nối Internet ổn định

### Cài đặt dependencies

```bash
# Clone repository
git clone <repository-url>
cd pair_trading_pro

# Tạo virtual environment
python -m venv venv
venv\Scripts\activate

# Cài đặt dependencies
pip install -r requirements.txt

# Hoặc cài đặt từ pyproject.toml
pip install -e .

# Cài đặt dev dependencies (cho developer)
pip install -e ".[dev]"

# Cài đặt visualization dependencies (tùy chọn)
pip install -e ".[viz]"
```

## Cấu hình

### 1. Tạo file cấu hình

```bash
# Copy file mẫu
cp .env.example .env
```

### 2. Chỉnh sửa .env

```env
# MT5 Configuration
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server

# Risk Management
MAX_DAILY_LOSS=1000.0
MAX_PORTFOLIO_LOSS=2000.0
MAX_SETUP_LOSS=500.0

# Trading Parameters
INITIAL_CAPITAL=10000.0
RISK_PER_TRADE=0.02
```

### 3. Cấu hình pairs trong config/

Chỉnh sửa file YAML trong thư mục `config/` để cấu hình các cặp giao dịch:

```yaml
# config/crypto_pairs.yaml
pairs:
  - name: "BTC-ETH"
    symbol_1: "BTCUSD"
    symbol_2: "ETHUSD"
    hedge_ratio: 0.05
    z_entry: 2.0
    z_exit: 0.5
    lookback_period: 60
```

## Sử dụng

### Khởi chạy GUI

```bash
python launch_gui.py
```

Giao diện GUI cung cấp:
- Biểu đồ giá và Z-score thời gian thực
- Giám sát vị thế hiện tại
- Thống kê rủi ro và P&L
- Controls để start/stop/pause giao dịch
- Log hoạt động

### Chạy CLI

```bash
# Giao dịch crypto pairs
python main_cli.py

# Giao dịch indices pairs
python main_indices_cli.py
```

### Backtest

```bash
# Sử dụng module backtest
cd backtest/
python run_backtest.py --config ../config/crypto_pairs.yaml --start-date 2024-01-01 --end-date 2024-12-31
```

## Testing

```bash
# Chạy tất cả tests
pytest

# Chạy với coverage report
pytest --cov=core --cov=strategy --cov=risk --cov-report=html

# Chạy test cụ thể
pytest tests/test_pyramid_execution_logic.py
```

## Luồng hoạt động

### 1. Khởi động
```
launch_gui.py → GUI Dashboard → MT5 Connection → Load Positions
```

### 2. Trading Loop
```
Data Manager → Signal Generator → Entry/Exit Decision → Risk Check → Order Execution
                      ↓
              Position Monitor → Hybrid Rebalancer → Pyramiding/Hedge Adjust
                      ↓
              Risk Manager → Trading Lock (nếu vi phạm)
```

### 3. Risk Management Flow
```
Check Per-Setup Loss → Check Portfolio Loss → Check Daily Loss
         ↓                      ↓                      ↓
    Within Limit?          Within Limit?         Within Limit?
         ↓                      ↓                      ↓
         └──────────────────────┴──────────────────────┘
                                ↓
                          Allow Trading
```

## Chiến lược Pair Trading

### Nguyên lý cơ bản

Pair trading dựa trên giả định rằng hai tài sản có tương quan sẽ quay về mức cân bằng (mean reversion). Hệ thống:

1. **Tính hedge ratio**: Tỷ lệ giao dịch tối ưu giữa hai tài sản
2. **Tính spread**: Price1 - hedge_ratio × Price2
3. **Chuẩn hóa spread thành Z-score**: (spread - mean) / std
4. **Tín hiệu giao dịch**:
   - Entry: |Z-score| > threshold (mặc định 2.0)
   - Exit: |Z-score| < exit_threshold (mặc định 0.5)

### Pyramiding & Hedge Adjustment

- **Pyramiding**: Tăng vị thế khi Z-score tăng (scale interval)
- **Hedge Adjustment**: Điều chỉnh tỷ lệ hedge khi drift vượt threshold
- **Volume Rebalancer**: Tự động cân bằng volume giữa hai leg

## Các thành phần chính

### Core Modules

- **data_manager**: Thu thập dữ liệu OHLCV từ MT5, tính toán chỉ báo
- **mt5_connector**: Wrapper cho MetaTrader5 API
- **position_monitor**: Theo dõi vị thế, P&L, margin
- **position_persistence**: Serialize/deserialize state vào JSON

### Strategy Modules

- **signal_generator**: Tính Z-score, phát tín hiệu entry/exit
- **hybrid_rebalancer**: Logic pyramiding + hedge adjustment
- **entry_cooldown**: Ngăn chặn entry trùng lặp trong khoảng thời gian ngắn

### Risk Modules

- **risk_manager**: Kiểm tra 3 lớp rủi ro
- **trading_lock_manager**: Quản lý khóa giao dịch tự động

### Executors

- **entry_executor**: Thực thi entry order (market/limit)
- **exit_executor**: Đóng vị thế
- **pyramiding_executor**: Scale in position
- **volume_rebalancer**: Điều chỉnh volume để duy trì hedge ratio

## Troubleshooting

### MT5 không kết nối được

```python
# Kiểm tra MT5 có đang chạy không
# Kiểm tra thông tin đăng nhập trong .env
# Đảm bảo AutoTrading được bật trong MT5
```

### Vị thế bị mất sau restart

```python
# Kiểm tra file positions/*.json có tồn tại không
# Đảm bảo position_persistence.py đang hoạt động
# Check log để thấy "State loaded successfully"
```

### Risk limit bị kích hoạt liên tục

```python
# Review lại giá trị MAX_DAILY_LOSS, MAX_PORTFOLIO_LOSS
# Kiểm tra sizing logic (có thể quá lớn)
# Xem log chi tiết trong logs/
```

## Roadmap

- [ ] Hỗ trợ multiple timeframes
- [ ] Machine learning để tối ưu hedge ratio
- [ ] Web dashboard (REST API + React frontend)
- [ ] Telegram bot notifications
- [ ] Cloud deployment support
- [ ] Advanced backtesting với slippage/commission models

## Đóng góp

Dự án này được phát triển cho mục đích nghiên cứu và giáo dục. Nếu bạn muốn đóng góp:

1. Fork repository
2. Tạo feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Tạo Pull Request

## License

Dự án được phân phối dưới MIT License. Xem file [LICENSE](LICENSE) để biết thêm chi tiết.

## Disclaimer

**CẢNH BÁO**: Giao dịch tài chính có rủi ro cao. Hệ thống này được cung cấp "AS IS" không có bất kỳ đảm bảo nào. Tác giả không chịu trách nhiệm cho bất kỳ tổn thất tài chính nào phát sinh từ việc sử dụng phần mềm này. Chỉ sử dụng với tài khoản demo hoặc số vốn bạn sẵn sàng mất.

**KHUYẾN NGHỊ**:
- Luôn test kỹ trên tài khoản demo trước
- Bắt đầu với vốn nhỏ
- Hiểu rõ chiến lược trước khi chạy tự động
- Giám sát thường xuyên
- Đặt stop-loss hợp lý

## Liên hệ

Để được hỗ trợ hoặc báo lỗi, vui lòng:
- Tạo issue trên GitHub
- Gửi email cho team phát triển

---

**Version**: 2.0.0
**Last Updated**: January 2024
**Maintained by**: Pair Trading Pro Team
