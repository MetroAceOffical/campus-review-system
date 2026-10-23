import { expect, it } from 'vitest'
import { codePointRangeToEditorRange } from '../src/editor/positions'
import type { DocumentNode } from '../src/types/document'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import OcrEvidence from '../src/components/OcrEvidence.vue'
const document: DocumentNode = { type: 'doc', content: [
  { type: 'paragraph', attrs: { nodeId: 'p1' }, content: [{ type: 'text', text: 'A😀' }, { type: 'text', text: '中x', marks: [{ type: 'bold' }] }] },
  { type: 'paragraph', attrs: { nodeId: 'p2' }, content: [{ type: 'text', text: 'B' }] },
] }
const map = [{ nodeId: 'p1', plainStart: 0, plainEnd: 2, nodeTextStart: 0, nodeTextEnd: 2 }, { nodeId: 'p1', plainStart: 2, plainEnd: 4, nodeTextStart: 2, nodeTextEnd: 4 }, { nodeId: 'p2', plainStart: 5, plainEnd: 6, nodeTextStart: 0, nodeTextEnd: 1 }]
it('maps emoji and cross-format evidence to UTF-16 editor positions without splitting surrogate pairs', () => {
  expect(codePointRangeToEditorRange(document, map, 1, 3)).toEqual([{ nodeId: 'p1', from: 2, to: 5, nodeFrom: 1, nodeTo: 4 }])
  expect(codePointRangeToEditorRange(document, map, 3, 6)).toEqual([{ nodeId: 'p1', from: 5, to: 6, nodeFrom: 4, nodeTo: 5 }, { nodeId: 'p2', from: 8, to: 9, nodeFrom: 0, nodeTo: 1 }])
})
it('shows empty OCR as recognition limitation and never as proof of no reuse', () => {
  const wrapper = mount(OcrEvidence, { props: { fileId: '1', result: { ocrStatus: 'EMPTY', recognitionLines: [], combinedText: '', textSearchStatus: 'NOT_RUN', qualityFlags: ['EMPTY_OCR'] } }, global: { plugins: [ElementPlus] } })
  try { expect(wrapper.text()).toContain('未识别到文字，未进行文字检索；不能据此判断无复用。'); expect(wrapper.text()).toContain('未运行'); expect(wrapper.text()).not.toContain('未发现复用') } finally { wrapper.unmount() }
})
