<!--
Vue 概念：`onMounted` 在组件挂载后初始化 ECharts，`watch` 监听 Chart Spec
变化并重新渲染，`onBeforeUnmount` 清理实例和 ResizeObserver。
-->
<script setup lang="ts">
import { Download } from '@lucide/vue'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { init, use } from 'echarts/core'
import type { ECharts, EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ChartSpec } from '../types/chat'
import {
  downloadDataUrl,
  exportTimestamp,
  safeExportName,
} from '../utils/export'

const props = defineProps<{
  spec: ChartSpec
}>()

use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
])

const chartElement = ref<HTMLDivElement | null>(null)
const canExport = ref(false)
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!chartElement.value) {
    return
  }
  chart = init(chartElement.value, undefined, { renderer: 'canvas' })
  renderChart()
  canExport.value = true
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartElement.value)
})

watch(
  () => props.spec,
  () => renderChart(),
  { deep: true },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
  canExport.value = false
})

function exportPng(): void {
  if (!chart) {
    return
  }
  const dataUrl = chart.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: '#ffffff',
  })
  downloadDataUrl(
    dataUrl,
    `${safeExportName(props.spec.title, 'datapilot-chart')}-${exportTimestamp()}.png`,
  )
}

function renderChart(): void {
  if (!chart) {
    return
  }
  const { spec } = props
  const common: EChartsCoreOption = {
    title: {
      text: spec.title,
      left: 8,
      textStyle: { color: '#17212b', fontSize: 14, fontWeight: 600 },
    },
    tooltip: { trigger: spec.type === 'pie' ? 'item' : 'axis' },
    grid: { left: 46, right: 24, top: 54, bottom: 42 },
    color: ['#0f766e', '#d97706', '#2563eb', '#be123c', '#4d7c0f'],
  }

  if (spec.type === 'pie') {
    const yField = spec.y_fields[0]
    chart.setOption(
      {
        ...common,
        series: [
          {
            type: 'pie',
            radius: ['36%', '68%'],
            data: spec.data.map((row) => ({
              name: String(row[spec.x_field]),
              value: Number(row[yField]),
            })),
          },
        ],
      } as EChartsCoreOption,
      true,
    )
    return
  }

  const xValues = spec.data.map((row) => String(row[spec.x_field]))
  const series = spec.y_fields.map((field) => ({
    name: field,
    type: spec.type === 'area' ? 'line' : spec.type,
    smooth: spec.type === 'line' || spec.type === 'area',
    areaStyle: spec.type === 'area' ? {} : undefined,
    data: spec.data.map((row) => Number(row[field])),
  }))

  chart.setOption(
    {
      ...common,
      xAxis: {
        type: spec.type === 'scatter' ? 'value' : 'category',
        data: spec.type === 'scatter' ? undefined : xValues,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: '#e2e8f0' } },
      },
      series,
    } as EChartsCoreOption,
    true,
  )
}
</script>

<template>
  <div class="chart-shell">
    <div class="chart-toolbar">
      <el-tooltip content="导出 PNG" placement="left">
        <el-button
          text
          :icon="Download"
          :disabled="!canExport"
          aria-label="导出 PNG"
          @click="exportPng"
        />
      </el-tooltip>
    </div>
    <div ref="chartElement" class="chart-view" role="img" :aria-label="spec.title"></div>
  </div>
</template>

<style scoped>
.chart-shell {
  display: grid;
  gap: 4px;
}

.chart-toolbar {
  display: flex;
  justify-content: flex-end;
}

.chart-view {
  width: 100%;
  height: 300px;
}
</style>
