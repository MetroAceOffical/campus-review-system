<script setup lang="ts">
import { computed } from 'vue'
import type { ExperimentBundle } from '../../api/experiments'
import { overview,type MetricKey } from './charts'
import ExperimentChart from './ExperimentChart.vue'
const props=defineProps<{bundle:ExperimentBundle;testSet:string;metric:MetricKey}>()
const charts=computed(()=>overview(props.bundle,props.testSet,props.metric))
</script>
<template><div class="experiment-grid"><ExperimentChart v-for="chart in charts" :key="chart.title" v-bind="chart" /></div></template>
