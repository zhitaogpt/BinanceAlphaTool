<!-- src/components/trading/TradingPanel.vue -->
<template>
  <div class="trading-panel bg-background text-foreground">
    <div class="panel-header flex justify-between items-center p-4 border-b">
      <h2 class="text-xl font-bold">幣安自動交易</h2>
      <Button
        variant="ghost"
        size="icon"
        @click="isMinimized = !isMinimized"
      >
        <Icon :name="isMinimized ? 'maximize' : 'minimize'" />
      </Button>
    </div>

    <div v-if="!isMinimized" class="panel-body p-4">
      <div class="config-section grid gap-4">
        <div class="form-group">
          <Label>源代幣</Label>
          <Input
            v-model="config.fromToken"
            placeholder="如：USDT"
          />
        </div>
        <div class="form-group">
          <Label>目標代幣</Label>
          <Input
            v-model="config.toToken"
            placeholder="如：B2"
          />
        </div>
        <div class="form-group">
          <Label>合約地址</Label>
          <Input
            v-model="config.contractAddress"
            placeholder="目標代幣合約地址"
          />
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="form-group">
            <Label>最小交易金額</Label>
            <Input
              v-model.number="config.minAmount"
              type="number"
              placeholder="最小交易金額"
            />
          </div>
          <div class="form-group">
            <Label>最大交易金額</Label>
            <Input
              v-model.number="config.maxAmount"
              type="number"
              placeholder="最大交易金額"
            />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="form-group">
            <Label>目標交易量</Label>
            <Input
              v-model.number="config.targetVolume"
              type="number"
              placeholder="總交易目標"
            />
          </div>
          <div class="form-group">
            <Label>最大損耗率</Label>
            <Input
              v-model.number="config.maxLossRate"
              type="number"
              step="0.001"
              placeholder="最大可接受損耗"
            />
          </div>
        </div>

        <div class="actions flex gap-4 mt-4">
          <Button
            @click="startTrading"
            :disabled="isTrading"
            class="flex-1"
            variant="default"
          >
            {{ isTrading ? '交易中' : '開始交易' }}
          </Button>
          <Button
            @click="stopTrading"
            :disabled="!isTrading"
            class="flex-1"
            variant="destructive"
          >
            停止交易
          </Button>
        </div>
      </div>

      <div class="stats-section mt-6 bg-secondary p-4 rounded-lg">
        <h3 class="text-lg font-semibold mb-4">交易統計</h3>
        <div class="grid grid-cols-2 gap-4">
          <div class="stat-item">
            <span class="text-muted-foreground">當前餘額</span>
            <strong>{{ stats.currentBalance.toFixed(2) }} USDT</strong>
          </div>
          <div class="stat-item">
            <span class="text-muted-foreground">總交易量</span>
            <strong>{{ stats.totalVolume.toFixed(2) }} USDT</strong>
          </div>
          <div class="stat-item">
            <span class="text-muted-foreground">已完成循環</span>
            <strong>{{ stats.cyclesCompleted }}</strong>
          </div>
          <div class="stat-item">
            <span class="text-muted-foreground">總損益</span>
            <strong :class="profitStatus">
              {{ stats.totalProfit.toFixed(4) }} USDT
            </strong>
          </div>
          <div class="stat-item col-span-2">
            <span class="text-muted-foreground">運行時間</span>
            <strong>{{ runningTime }}</strong>
          </div>
        </div>
      </div>

      <div class="logs-section mt-6 bg-muted p-4 rounded-lg max-h-48 overflow-y-auto">
        <h3 class="text-lg font-semibold mb-4">交易日誌</h3>
        <div
          v-for="(log, index) in logs"
          :key="index"
          class="log-item text-sm py-1 border-b last:border-b-0"
          :class="{
            'text-destructive': log.includes('❌'),
            'text-success': log.includes('✅'),
            'text-warning': log.includes('⚠️')
          }"
        >
          {{ log }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useTradingStore } from '@/services/trading/tradingService'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Icon } from '@iconify/vue'

// 使用交易商店
const tradingStore = useTradingStore()

// 解構需要的狀態和方法
const {
  config,
  stats,
  logs,
  isTrading,
  runningTime,
  profitStatus,
  startTrading,
  stopTrading,
  saveConfig,
  loadConfig
} = tradingStore

// 最小化狀態
const isMinimized = ref(false)

// 生命週期掛載
onMounted(() => {
  // 載入保存的配置
  loadConfig()
})

// 監聽配置變化並保存
watch(config, () => {
  saveConfig()
}, { deep: true })

// 計算損益狀態的CSS類
const profitStatusClass = computed(() =>
  stats.totalProfit >= 0 ? 'text-success' : 'text-destructive'
)
</script>

<style scoped>
.stat-item {
  display: flex;
  flex-direction: column;
}

.stat-item span {
  font-size: 0.75rem;
  margin-bottom: 0.25rem;
}

.stat-item strong {
  font-size: 1rem;
}

.log-item {
  word-break: break-all;
  white-space: normal;
}
</style>