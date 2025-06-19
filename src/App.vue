<!-- src/App.vue -->
<script setup>
import { ref, onMounted, computed } from 'vue';
import TradingPanel from '@/components/trading/TradingPanel.vue';
import { useTradingStore } from '@/services/trading/tradingService';
import { Toaster } from '@/components/ui/toast';

const tradingStore = useTradingStore();
const isMinimized = ref(false);

// 容器樣式計算
const containerStyle = computed(() => ({
  position: isMinimized.value ? 'fixed' : 'relative',
  transform: isMinimized.value ? 'none' : undefined,
  height: isMinimized.value ? '0' : '100%',
  width: '100%',
  zIndex: 10001
}));

// 視窗縮放處理
const handleResize = () => {
  const scale = window.innerWidth <= 768 ? '0.9' : '1';
  document.documentElement.style.setProperty('--app-scale', scale);

  const vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
};

// 生命週期掛載
onMounted(() => {
  handleResize();
  window.addEventListener('resize', handleResize);

  // 防止頁面橡皮筋效果
  document.body.addEventListener('touchmove', (e) => {
    if (e.touches.length > 1) {
      e.preventDefault();
    }
  }, { passive: false });

  return () => {
    window.removeEventListener('resize', handleResize);
  };
});

// 最小化切換處理
const handleMinimizeChange = (minimized) => {
  isMinimized.value = minimized;
};
</script>

<template>
  <div>
    <Toaster />
    <div class="app-container" :style="containerStyle">
      <TradingPanel
        class="trading-panel"
        @minimize-change="handleMinimizeChange"
      />
    </div>

    <!-- 全局工具欄 -->
    <div class="fixed bottom-4 right-4 z-50 flex gap-2">
      <!-- 交易狀態指示器 -->
      <div
        v-if="tradingStore.isTrading"
        class="p-2 bg-green-500 text-white rounded-full animate-pulse"
      >
        🔄
      </div>
    </div>
  </div>
</template>

<style>
:root {
  --app-scale: 1;
  --vh: 1vh;
}

.app-container {
  font-family: 'Inter', 'Arial', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  transition: all 0.3s ease;
}

.trading-panel {
  transform: scale(var(--app-scale));
  transform-origin: center;
  pointer-events: auto;
  height: 100%;
  width: 100%;
}

/* 響應式適配 */
@media (max-width: 768px) {
  .app-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    overflow: hidden;
  }
}

/* 觸控與交互優化 */
* {
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
  user-select: none;
}
</style>