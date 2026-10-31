import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './style.css'
import './styles/design.css'
import './styles/density.css'
import App from './App.vue'
import { router } from './router'
import { applyTheme, readTheme } from './theme'

applyTheme(readTheme())
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => applyTheme(readTheme()))
createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
