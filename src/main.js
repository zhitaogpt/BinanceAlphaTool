// src/main.js
import '@/styles/tailwind.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from '@/App.vue'
import { useTradingStore } from '@/services/trading/tradingService';

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)

const mount = () => {
  let container = document.getElementById('binance-trading-app')

  if (!container) {
    container = document.createElement('div')
    container.id = 'binance-trading-app'
    document.body.appendChild(container)
  }

  app.mount('#binance-trading-app')

  // 在开发模式下添加调试信息
  if (import.meta.env.DEV) {
    window.__APP__ = app
    window.__PINIA__ = pinia
    window.__TRADING_STORE__ = useTradingStore()
  }
}

// 防止頁面默認事件
document.addEventListener('DOMContentLoaded', () => {
  document.body.addEventListener('touchmove', (e) => {
    if (e.touches.length > 1) {
      e.preventDefault()
    }
  }, { passive: false })
})

mount()