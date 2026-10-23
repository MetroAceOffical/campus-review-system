import { expect, it } from 'vitest'
import { applyTheme, contrastRatio } from '../src/theme'

it('keeps readable primary buttons for light and dark custom colors', () => {
  for (const primary of ['#ffffff', '#000000', '#ffff00', '#1463bc']) {
    applyTheme({ mode: 'light', primary })
    const root = document.documentElement.style
    expect(contrastRatio(root.getPropertyValue('--el-color-primary'), root.getPropertyValue('--primary-text'))).toBeGreaterThanOrEqual(4.5)
  }
})
