// src/services/trading/tradingService.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import CryptoJS from 'crypto-js'

export interface TradeConfig {
  fromToken: string
  toToken: string
  contractAddress: string
  minAmount: number
  maxAmount: number
  targetVolume: number
  maxLossRate: number
  minUSDTRequired: number
}

export interface TradeRecord {
  time: string
  buyAmount: number
  sellAmount: number
  profitLoss: number
  cycleNumber: number
}

export const useTradingStore = defineStore('trading', () => {
  // 配置
  const config = ref<TradeConfig>({
    fromToken: 'USDT',
    toToken: 'B2',
    contractAddress: '0x783c3f003f172c6ac5ac700218a357d2d66ee2a2',
    minAmount: 10,
    maxAmount: 20,
    targetVolume: 8192,
    maxLossRate: 0.004,
    minUSDTRequired: 50
  })

  // 交易狀態
  const stats = ref({
    startBalance: 0,
    currentBalance: 0,
    totalVolume: 0,
    cyclesCompleted: 0,
    totalProfit: 0,
    tradeHistory: [] as TradeRecord[],
    startTime: 0,
    lastUpdated: 0
  })

  // 交易日誌
  const logs = ref<string[]>([])
  const isTrading = ref(false)
  const isConnected = ref(false)

  // 運行時間計算
  const runningTime = computed(() => {
    if (stats.value.startTime === 0) return '00:00:00'
    const runningTime = Date.now() - stats.value.startTime
    const hours = Math.floor(runningTime / (1000 * 60 * 60))
    const minutes = Math.floor((runningTime % (1000 * 60 * 60)) / (1000 * 60))
    const seconds = Math.floor((runningTime % (1000 * 60)) / 1000)
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  })

  // 損益狀態
  const profitStatus = computed(() =>
    stats.value.totalProfit >= 0 ? 'positive' : 'negative'
  )

  // MD5加密函數（用於生成CSRF Token）
  function MD5(str: string): string {
    return CryptoJS.MD5(str).toString()
  }

  // 獲取Cookies值
  function getCookieValue(name: string): string | null {
    const cookies = document.cookie.split(';')
    for (let cookie of cookies) {
      cookie = cookie.trim()
      if (cookie.startsWith(`${name}=`)) {
        return cookie.substring(name.length + 1)
      }
    }
    return null
  }

  // 準備請求頭
  function getHeaders() {
    const cr00 = getCookieValue('cr00')
    if (!cr00) {
      throw new Error('無法找到cr00 cookie')
    }
    const csrftoken = MD5(cr00)

    return {
      "Accept": "*/*",
      "Content-Type": "application/json",
      "clienttype": "web",
      "csrftoken": csrftoken
    }
  }

  // 獲取報價
  async function getQuote(params: Record<string, any>) {
    try {
      const response = await axios.post(
        'https://www.binance.com/bapi/defi/v1/private/wallet-direct/swap/cex/get-quote',
        params,
        { headers: getHeaders() }
      )
      return response.data.data
    } catch (error) {
      logs.value.push(`❌ 獲取報價錯誤: ${error}`)
      return null
    }
  }

  // 買入代幣
  async function buyToken(params: Record<string, any>) {
    try {
      const response = await axios.post(
        'https://www.binance.com/bapi/defi/v2/private/wallet-direct/swap/cex/buy/pre/payment',
        params,
        { headers: getHeaders() }
      )
      return response.data
    } catch (error) {
      logs.value.push(`❌ 買入代幣錯誤: ${error}`)
      return { success: false, message: error }
    }
  }

  // 賣出代幣
  async function sellToken(params: Record<string, any>) {
    try {
      const response = await axios.post(
        'https://www.binance.com/bapi/defi/v2/private/wallet-direct/swap/cex/sell/pre/payment',
        params,
        { headers: getHeaders() }
      )
      return response.data
    } catch (error) {
      logs.value.push(`❌ 賣出代幣錯誤: ${error}`)
      return { success: false, message: error }
    }
  }

  // 獲取餘額
  async function getUSDTBalance() {
    try {
      const response = await axios.get(
        'https://www.binance.com/bapi/asset/v2/private/asset-service/wallet/balance?quoteAsset=USDT&needBalanceDetail=true&needEuFuture=true',
        { headers: getHeaders() }
      )
      const spotAccount = response.data.data.find((account: any) => account.accountType === "MAIN")
      const usdt = spotAccount?.assetBalances.find((asset: any) => asset.asset === "USDT")
      return usdt ? parseFloat(usdt.free) : 0
    } catch (error) {
      logs.value.push(`❌ 獲取USDT餘額錯誤: ${error}`)
      return 0
    }
  }

  // 單次交易循環
  async function runCycle() {
    try {
      // 檢查USDT餘額
      const usdtBalance = await getUSDTBalance()
      stats.value.currentBalance = usdtBalance

      if (usdtBalance < config.value.minUSDTRequired) {
        logs.value.push(`⚠️ USDT餘額不足: ${usdtBalance} < ${config.value.minUSDTRequired}`)
        return false
      }

      // 買入操作
      const fromToken = config.value.fromToken
      const toToken = config.value.toToken
      const fromAmount = Math.random() * (config.value.maxAmount - config.value.minAmount) + config.value.minAmount

      logs.value.push(`🔄 開始第 ${stats.value.cyclesCompleted + 1} 輪交易，買入金額：${fromAmount} ${fromToken}`)

      // 獲取買入報價
      const buyQuote = await getQuote({
        fromToken,
        fromBinanceChainId: '56', // BSC
        fromCoinAmount: fromAmount,
        toToken,
        toBinanceChainId: '56',
        toContractAddress: config.value.contractAddress,
        priorityMode: "priorityOnCustom",
        customNetworkFeeMode: "priorityOnSuccess",
        customSlippage: "0.001"
      })

      if (!buyQuote) return false

      // 執行買入
      const buyResult = await buyToken({
        fromToken,
        fromBinanceChainId: '56',
        fromCoinAmount: fromAmount,
        toToken,
        toContractAddress: config.value.contractAddress,
        toCoinAmount: buyQuote.toCoinAmount,
        priorityMode: "priorityOnPrice",
        extra: buyQuote.extra
      })

      if (!buyResult.success) {
        logs.value.push(`❌ 買入失敗: ${buyResult.message}`)
        return false
      }

      // 賣出操作
      const sellQuote = await getQuote({
        fromToken: toToken,
        fromBinanceChainId: '56',
        fromContractAddress: config.value.contractAddress,
        fromCoinAmount: buyQuote.toCoinAmount,
        toToken: fromToken,
        toBinanceChainId: '56',
        toContractAddress: '',
        priorityMode: "priorityOnCustom",
        customNetworkFeeMode: "priorityOnSuccess",
        customSlippage: "0.001"
      })

      if (!sellQuote) return false

      const sellResult = await sellToken({
        fromToken: toToken,
        fromBinanceChainId: '56',
        fromContractAddress: config.value.contractAddress,
        fromCoinAmount: buyQuote.toCoinAmount,
        toToken: fromToken,
        toBinanceChainId: '56',
        toCoinAmount: sellQuote.toCoinAmount,
        priorityMode: "priorityOnPrice",
        extra: sellQuote.extra
      })

      if (!sellResult.success) {
        logs.value.push(`❌ 賣出失敗: ${sellResult.message}`)
        return false
      }

      // 更新統計
      const newTrade: TradeRecord = {
        time: new Date().toISOString(),
        buyAmount: fromAmount,
        sellAmount: sellQuote.toCoinAmount,
        profitLoss: sellQuote.toCoinAmount - fromAmount,
        cycleNumber: stats.value.cyclesCompleted + 1
      }

      stats.value.tradeHistory.push(newTrade)
      stats.value.totalVolume += fromAmount
      stats.value.totalProfit += newTrade.profitLoss
      stats.value.cyclesCompleted++
      stats.value.lastUpdated = Date.now()

      logs.value.push(`✅ 交易成功：買入 ${fromAmount} ${fromToken}，賣出獲得 ${sellQuote.toCoinAmount} ${fromToken}`)

      return true
    } catch (error) {
      logs.value.push(`❌ 交易循環錯誤: ${error}`)
      return false
    }
  }

  // 開始交易
  async function startTrading() {
    if (isTrading.value) return

    isTrading.value = true
    stats.value.startTime = Date.now()
    logs.value.push('🚀 開始自動交易')

    while (isTrading.value && stats.value.totalVolume < config.value.targetVolume) {
      const success = await runCycle()

      if (!success) {
        logs.value.push('⚠️ 交易循環失敗，等待30秒後重試')
        await new Promise(resolve => setTimeout(resolve, 30000))
      }

      // 每輪交易間隔60秒
      await new Promise(resolve => setTimeout(resolve, 60000))
    }

    stopTrading()
  }

  // 停止交易
  function stopTrading() {
    isTrading.value = false
    logs.value.push('⏹️ 停止交易')
  }

  // 保存配置
  function saveConfig() {
    localStorage.setItem('tradingConfig', JSON.stringify(config.value))
  }

  // 載入配置
  function loadConfig() {
    const savedConfig = localStorage.getItem('tradingConfig')
    if (savedConfig) {
      config.value = JSON.parse(savedConfig)
    }
  }

  // 生成報告
  function generateReport() {
    const reportData = {
      timestamp: new Date().toISOString(),
      startBalance: stats.value.startBalance,
      currentBalance: stats.value.currentBalance,
      totalVolume: stats.value.totalVolume,
      cyclesCompleted: stats.value.cyclesCompleted,
      totalProfit: stats.value.totalProfit,
      trades: stats.value.tradeHistory
    }

    const report = `
幣安自動交易報告 - ${new Date().toLocaleString()}
========================================
開始餘額: ${reportData.startBalance.toFixed(2)} USDT
當前餘額: ${reportData.currentBalance.toFixed(2)} USDT
總交易量: ${reportData.totalVolume.toFixed(2)} USDT
已完成循環: ${reportData.cyclesCompleted}
總損益: ${reportData.totalProfit.toFixed(4)} USDT
    `

    return report
  }

  return {
    config,
    stats,
    logs,
    isTrading,
    isConnected,
    runningTime,
    profitStatus,
    startTrading,
    stopTrading,
    saveConfig,
    loadConfig,
    generateReport
  }
})