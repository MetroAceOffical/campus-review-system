import { expect, it } from 'vitest'
import { codePointRangeToEditorRange } from '../src/editor/positions'
import type { DocumentNode } from '../src/types/document'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import OcrEvidence from '../src/components/OcrEvidence.vue'
import TextEvidence from '../src/components/TextEvidence.vue'
import type { TextEvidenceItem } from '../src/api/review'

it('shows a semantic warning separately from literal acceptance and supports old reports', () => {
  const evidence: TextEvidenceItem = { evidenceId: 'new', evidenceType: 'TEXT_SIMILARITY', sourceWorkId: '1', sourceRevisionId: '1',
    sourceTitle: '测试来源', sourceKind: 'BODY', acceptedCandidate: false, literalAcceptedCandidate: false, tfidfScore: .4,
    literalSummary: { matched_characters: 0, query_character_coverage: 0, longest_match: 0 }, matches: [], semanticWindows: [],
    semanticSummary: { suspectedReuse: true, supportingPairs: 2, matchedQueryCharacters: 80, status: 'EVALUATED' } }
  const wrapper = mount(TextEvidence, { props: { evidence: [evidence] }, global: { plugins: [ElementPlus] } })
  expect(wrapper.text()).toContain('疑似语义复用')
  expect(wrapper.find('.evidence-metrics').text()).toContain('80')
  expect(wrapper.find('.evidence-metrics').text()).not.toContain('字面重复')
  expect(wrapper.text()).not.toContain('符合字面证据条件')
  wrapper.unmount()
  const old = { ...evidence, semanticSummary: undefined }
  const previous = mount(TextEvidence, { props: { evidence: [old] }, global: { plugins: [ElementPlus] } })
  expect(previous.text()).toContain('相近来源')
  expect(previous.get('[data-testid="other-text-candidates"]').element.hasAttribute('open')).toBe(false)
  expect(previous.findAll('.el-tag').some(tag => tag.text() === '疑似语义复用')).toBe(false)
  previous.unmount()
})
const document: DocumentNode = { type: 'doc', content: [
  { type: 'paragraph', attrs: { nodeId: 'p1' }, content: [{ type: 'text', text: 'A😀' }, { type: 'text', text: '中x', marks: [{ type: 'bold' }] }] },
  { type: 'paragraph', attrs: { nodeId: 'p2' }, content: [{ type: 'text', text: 'B' }] },
] }
const map = [{ nodeId: 'p1', plainStart: 0, plainEnd: 2, nodeTextStart: 0, nodeTextEnd: 2 }, { nodeId: 'p1', plainStart: 2, plainEnd: 4, nodeTextStart: 2, nodeTextEnd: 4 }, { nodeId: 'p2', plainStart: 5, plainEnd: 6, nodeTextStart: 0, nodeTextEnd: 1 }]
it('maps emoji and cross-format evidence to UTF-16 editor positions without splitting surrogate pairs', () => {
  expect(codePointRangeToEditorRange(document, map, 1, 3)).toEqual([{ nodeId: 'p1', from: 2, to: 5, nodeFrom: 1, nodeTo: 4 }])
  expect(codePointRangeToEditorRange(document, map, 3, 6)).toEqual([{ nodeId: 'p1', from: 5, to: 6, nodeFrom: 4, nodeTo: 5 }, { nodeId: 'p2', from: 8, to: 9, nodeFrom: 0, nodeTo: 1 }])
})
it('shows empty recognition and skipped search without reporting a match', () => {
  const wrapper = mount(OcrEvidence, { props: { fileId: '1', result: { ocrStatus: 'EMPTY', recognitionLines: [], combinedText: '', textSearchStatus: 'NOT_RUN', qualityFlags: ['EMPTY_OCR'] } }, global: { plugins: [ElementPlus] } })
  try { expect(wrapper.text()).toContain('未识别到文字'); expect(wrapper.text()).toContain('未运行'); expect(wrapper.text()).not.toContain('未发现复用') } finally { wrapper.unmount() }
})
