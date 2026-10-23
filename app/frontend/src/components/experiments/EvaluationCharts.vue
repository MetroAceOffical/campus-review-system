<script setup lang="ts">
import { computed } from 'vue'
import type { ExperimentBundle } from '../../api/experiments'
import { evaluation } from './charts'
import ExperimentChart from './ExperimentChart.vue'
const props=defineProps<{bundle:ExperimentBundle;testSet:string;model:string}>()
const charts=computed(()=>evaluation(props.bundle,props.testSet,props.model))
</script>
<template><div class="experiment-grid"><ExperimentChart v-for="chart in charts" :key="chart.title" v-bind="chart" /></div></template>
