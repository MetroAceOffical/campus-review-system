export interface Theme { mode: 'light' | 'dark' | 'system'; primary: string }
const defaults: Theme = { mode: 'light', primary: '#215dba' }
function rgb(hex: string) { return [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16)) }
function luminance(hex: string) {
  const [r, g, b] = rgb(hex).map(value => { const s = value / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4 })
  return .2126 * r! + .7152 * g! + .0722 * b!
}
export function contrastRatio(a: string, b: string) { const values = [luminance(a), luminance(b)].sort((x, y) => y - x); return (values[0]! + .05) / (values[1]! + .05) }
export function readTheme(): Theme {
  try {
    const stored = JSON.parse(localStorage.getItem('campus-theme') ?? '{}')
    return { mode: ['light', 'dark', 'system'].includes(stored.mode) ? stored.mode : defaults.mode, primary: /^#[0-9a-f]{6}$/i.test(stored.primary) ? stored.primary : defaults.primary }
  } catch { return { ...defaults } }
}
export function applyTheme(theme: Theme) {
  const dark = theme.mode === 'dark' || (theme.mode === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  const canvas = dark ? '#161b22' : '#ffffff'
  let primary = /^#[0-9a-f]{6}$/i.test(theme.primary) ? theme.primary : defaults.primary
  for (let i = 0; contrastRatio(primary, canvas) < 4.5 && i < 50; i++) {
    primary = '#' + rgb(primary).map(channel => Math.round(channel * .9 + (dark ? 255 : 0) * .1).toString(16).padStart(2, '0')).join('')
  }
  const root = document.documentElement
  root.classList.toggle('dark', !!dark)
  root.style.setProperty('--el-color-primary', primary)
  root.style.setProperty('--primary-text', contrastRatio(primary, '#ffffff') >= 4.5 ? '#ffffff' : '#000000')
  localStorage.setItem('campus-theme', JSON.stringify(theme))
}
