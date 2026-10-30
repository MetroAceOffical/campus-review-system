<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  home: 'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
  data: 'M4 5c0-4 16-4 16 0s-16 4-16 0Zm0 0v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0',
  train: 'M4 20V10m5 10V4m6 16v-7m5 7V7M2 22h20',
  model: 'm12 2 10 5-10 5L2 7l10-5ZM2 12l10 5 10-5M2 17l10 5 10-5',
  release: 'M12 16V3m-5 5 5-5 5 5M4 14v7h16v-7',
  library: 'M4 3h4v18H4V3Zm7 0h4v18h-4V3Zm7 1 3-1 3 17-3 1-3-17',
  settings: 'M3 6h18M3 12h18M3 18h18M8 3v6m8 0v6m-6 0v6',
  document: 'M5 2h10l4 4v16H5V2Zm9 0v5h5M8 11h8m-8 4h8m-8 4h5',
  edit: 'm4 16 12-12 4 4L8 20l-5 1 1-5Zm10-10 4 4',
  review: 'M12 3 3 7v6c0 5 9 9 9 9s9-4 9-9V7l-9-4Zm-5 9 3 3 7-7',
  image: 'M3 3h18v18H3V3Zm0 14 6-7 5 6 3-4 4 5M16 7h.01',
  grammar: 'M3 18 9 3l6 15M5 13h8m2 7 3 3 5-7',
  search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6',
  menu: 'M3 6h18M3 12h18M3 18h18',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  check: 'm4 12 5 5L20 6',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v6l4 2',
  upload: 'M12 16V3m-5 5 5-5 5 5M3 16v5h18v-5',
  clean: 'm13 3 8 8M16 6 4 18l4 4L20 10M3 22h18M4 4v6m-3-3h6',
  link: 'm9 15 6-6M7 14l-2 2a4 4 0 0 0 6 6l3-3M10 5l3-3a4 4 0 0 1 6 6l-2 2',
  help: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM9 8a3 3 0 0 1 6 0c0 3-3 2-3 5m0 4h.01',
}
</script>
<template><svg class="app-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.document" /></svg></template>
