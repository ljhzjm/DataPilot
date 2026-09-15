<!--
Vue 概念：`onMounted` 在组件挂载后初始化 ECharts，`watch` 监听 Chart Spec
变化并重新渲染，`onBeforeUnmount` 清理实例和 ResizeObserver。
-->
<script setup lang="ts">
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ChartSpec } from '../types/chat'

const props = defineProps<{
  spec: ChartSpec
}>()

const chartElement = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!chartElement.value) {
    return
  }
  chart = echarts.init(chartElement.value, undefined, { renderer: 'canvas' })
  renderChart()
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
})

function renderChart(): void {
  if (!chart) {
    return
  }
  const { spec } = props
  const common: EChartsOption = {
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
      } as EChartsOption,
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
    } as EChartsOption,
    true,
  )
}
</script>

<template>
  <div ref="chartElement" class="chart-view" role="img" :aria-label="spec.title"></div>
</template>

<style scoped>
.chart-view {
  width: 100%;
  height: 300px;
}
</style>
