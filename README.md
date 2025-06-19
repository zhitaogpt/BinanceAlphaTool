# Binance Alpha Trading Tool

#### 

## 中文 (Chinese) Readme made by AI

### ⚠️ 免責聲明
**此專案為個人自用工具，已停止維護更新。使用前請仔細閱讀風險提示。**

### 專案簡介
Binance Alpha Trading Tool 是一個基於Vue 3開發的油猴腳本，**專門用於刷Binance Alpha積分的自動化工具**。該工具會自動執行買進後立即賣出的操作來累積交易量，幫助用戶達到設定的目標交易額以獲取Alpha積分。工具提供可視化交易面板，並具備完整的交易記錄功能。

### 核心用途
- 🎯 **Alpha積分累積**: 專門設計用於刷取Binance Alpha積分
- 🔄 **快速交易循環**: 買進後立即賣出，最大化交易頻率
- 📈 **目標導向**: 可設定目標交易量，自動達成積分要求
- 📊 **交易追踪**: 完整記錄每筆交易，方便查看進度

### 主要功能
- 🤖 **自動交易循環**: 自動執行買入/賣出操作
- 💰 **智能金額控制**: 可設定最小/最大交易金額
- 📊 **實時統計監控**: 顯示交易統計、損益狀況
- 🔄 **風險控制**: 設定最大損耗率保護
- 📝 **交易日誌**: 詳細記錄每筆交易狀況
- 💾 **配置保存**: 自動保存用戶配置設定
- 📱 **響應式設計**: 支持桌面和移動設備

### 技術架構
- **前端框架**: Vue 3 + Composition API
- **狀態管理**: Pinia
- **UI 組件**: 自定義組件 + Tailwind CSS
- **HTTP 請求**: Axios
- **加密處理**: CryptoJS (MD5)
- **構建工具**: Vite + vite-plugin-monkey
- **包管理**: PNPM

### 目錄結構
```
binance-alpha-tool/
├── src/
│   ├── App.vue                    # 主應用組件
│   ├── main.js                    # 應用入口
│   ├── injectProd.js             # 生產環境注入腳本
│   ├── injectDev.js              # 開發環境注入腳本
│   ├── components/
│   │   └── trading/
│   │       └── TradingPanel.vue  # 交易面板組件
│   ├── services/
│   │   └── trading/
│   │       └── tradingService.ts # 交易服務邏輯
│   └── styles/
│       └── tailwind.css          # 樣式文件
├── vite.config.js                # Vite 配置
├── package.json                  # 項目依賴
└── README.md                     # 說明文檔
```

### 核心邏輯
1. **頁面API交易**: 直接在Binance頁面上使用API進行交易，無需手動F12獲取Cookies
2. **自動認證**: 通過讀取頁面現有的cr00 cookie自動生成CSRF token
3. **即買即賣**: 獲取報價後立即執行買入，成功後馬上賣出
4. **目標追踪**: 累積交易量直到達到設定的目標交易額
5. **風控穩定**: 連續使用一週無風控驗證觸發，運行穩定可靠

### 使用體驗
- ✅ **操作簡便**: 在Binance頁面直接運行，無需複雜設置
- ✅ **穩定可靠**: 測試一週運行無風控問題
- ✅ **自動化程度高**: 設定好參數後可無人值守運行
- ✅ **實時反饋**: 即時顯示交易進度和積分累積狀況

### 安裝使用
1. 安裝油猴腳本管理器 (Tampermonkey, Greasemonkey等)
2. 複製生成的 `.user.js` 文件內容
3. 在腳本管理器中創建新腳本並貼上內容
4. 訪問Binance網站，工具會自動載入

### 風險警告
- ⚠️ **高風險投資**: 加密貨幣交易具有極高風險
- ⚠️ **資金安全**: 請勿在主帳戶使用，建議小額測試
- ⚠️ **API變動**: Binance API可能隨時變更導致腳本失效
- ⚠️ **法律合規**: 請確保在當地法律允許範圍内使用
- ⚠️ **無保證**: 開發者不對任何損失承擔責任

---

## English Readme made by AI

### ⚠️ Disclaimer
**This project is a personal tool for individual use only and is no longer maintained or updated. Please read the risk warnings carefully before use.**

### Project Overview
Binance Alpha Trading Tool is a Vue 3-based userscript **specifically designed for farming Binance Alpha points**. The tool automatically executes buy-then-immediately-sell operations to accumulate trading volume, helping users reach their target trading amounts to earn Alpha points. It features a visual trading panel with comprehensive transaction logging.

### Primary Purpose
- 🎯 **Alpha Points Farming**: Specifically designed for accumulating Binance Alpha points
- 🔄 **Rapid Trading Cycles**: Buy and immediately sell to maximize trading frequency
- 📈 **Goal-Oriented**: Set target trading volumes to automatically meet point requirements
- 📊 **Transaction Tracking**: Complete logging of every trade for progress monitoring

### Key Features
- 🤖 **Automated Trading Cycles**: Automatically execute buy/sell operations
- 💰 **Smart Amount Control**: Configurable minimum/maximum trading amounts
- 📊 **Real-time Statistics**: Display trading statistics and profit/loss status
- 🔄 **Risk Management**: Set maximum loss rate protection
- 📝 **Trading Logs**: Detailed logging of every transaction
- 💾 **Configuration Persistence**: Automatically save user settings
- 📱 **Responsive Design**: Support for desktop and mobile devices

### Technology Stack
- **Frontend Framework**: Vue 3 + Composition API
- **State Management**: Pinia
- **UI Components**: Custom components + Tailwind CSS
- **HTTP Requests**: Axios
- **Encryption**: CryptoJS (MD5)
- **Build Tools**: Vite + vite-plugin-monkey
- **Package Manager**: PNPM

### Project Structure
```
binance-alpha-tool/
├── src/
│   ├── App.vue                    # Main application component
│   ├── main.js                    # Application entry point
│   ├── injectProd.js             # Production injection script
│   ├── injectDev.js              # Development injection script
│   ├── components/
│   │   └── trading/
│   │       └── TradingPanel.vue  # Trading panel component
│   ├── services/
│   │   └── trading/
│   │       └── tradingService.ts # Trading service logic
│   └── styles/
│       └── tailwind.css          # Styling
├── vite.config.js                # Vite configuration
├── package.json                  # Project dependencies
└── README.md                     # Documentation
```

### Core Logic
1. **Page-Based API Trading**: Direct API trading on Binance page without manual F12 cookie extraction
2. **Automatic Authentication**: Auto-generate CSRF token by reading existing cr00 cookie from page
3. **Instant Buy-Sell**: Execute buy order immediately followed by sell order
4. **Goal Tracking**: Accumulate trading volume until reaching set target amount
5. **Risk Control Stable**: Tested for one week without triggering risk control verification

### User Experience
- ✅ **Simple Operation**: Runs directly on Binance page without complex setup
- ✅ **Stable & Reliable**: One week of testing without risk control issues
- ✅ **High Automation**: Unattended operation after parameter setup
- ✅ **Real-time Feedback**: Live display of trading progress and point accumulation

### Installation & Usage
1. Install a userscript manager (Tampermonkey, Greasemonkey, etc.)
2. Copy the generated `.user.js` file content
3. Create a new script in the script manager and paste the content
4. Visit Binance website, the tool will load automatically

### Risk Warnings
- ⚠️ **High-Risk Investment**: Cryptocurrency trading involves extremely high risks
- ⚠️ **Fund Security**: Do not use with main accounts, recommend small amount testing
- ⚠️ **API Changes**: Binance API may change at any time causing script failure
- ⚠️ **Legal Compliance**: Ensure usage complies with local laws and regulations
- ⚠️ **No Guarantee**: Developer assumes no responsibility for any losses

---

## Development Commands

```bash
# Install dependencies
pnpm install

# Development mode
pnpm run dev

# Build for production
pnpm run build

# Preview build
pnpm run preview

# Lint code
pnpm run lint

# Format code
pnpm run format
```

## License
ISC License - For personal use only. No commercial use permitted.

## Status
🚫 **No longer maintained** - This project is provided as-is without ongoing support or updates.