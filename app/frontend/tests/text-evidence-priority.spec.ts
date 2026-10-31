import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, it } from 'vitest'
import TextEvidence from '../src/components/TextEvidence.vue'
import type { TextEvidenceItem } from '../src/api/review'

it('highlights actual semantic evidence and collapses unrelated retrieved candidates',()=>{
  const base={evidenceType:'TEXT_SIMILARITY',evidenceId:'semantic',sourceWorkId:'1',sourceRevisionId:'2',sourceTitle:'课程原稿',sourceKind:'BODY',tfidfScore:.4,acceptedCandidate:false,literalSummary:{matched_characters:0,query_character_coverage:0,longest_match:0},matches:[],semanticWindows:[{queryStart:0,queryEnd:20,queryText:'投稿对应片段',sourceText:'来源对应片段',score:.8,citationSupport:true}],semanticSummary:{suspectedReuse:true,supportingPairs:16,matchedQueryCharacters:399,status:'EVALUATED'}} as TextEvidenceItem
  const candidate={...base,evidenceId:'candidate',sourceTitle:'仅检索相近的另一篇稿件',semanticWindows:[],semanticSummary:{...base.semanticSummary!,suspectedReuse:false,supportingPairs:0,matchedQueryCharacters:0}}
  const wrapper=mount(TextEvidence,{props:{evidence:[candidate,base],allowLocate:true},global:{plugins:[ElementPlus],stubs:{OcrEvidence:true}}})
  const primary=wrapper.get('[data-testid="primary-text-evidence"]')
  expect(primary.text()).toContain('16')
  expect(primary.text()).toContain('399')
  expect(primary.find('.evidence-metrics').text()).not.toContain('字面重复字符')
  expect(wrapper.get('[data-testid="other-text-candidates"]').element.hasAttribute('open')).toBe(false)
  wrapper.unmount()
})

it('keeps zero literal counters out of the main metric cards even in old cited reports',()=>{
  const item={evidenceType:'TEXT_SIMILARITY',evidenceId:'old',sourceWorkId:'1',sourceRevisionId:'2',sourceTitle:'旧来源',sourceKind:'BODY',tfidfScore:.2,acceptedCandidate:false,fullyCited:true,literalSummary:{matched_characters:0,query_character_coverage:0,longest_match:0},matches:[],semanticWindows:[]} as TextEvidenceItem
  const wrapper=mount(TextEvidence,{props:{evidence:[item]},global:{plugins:[ElementPlus],stubs:{OcrEvidence:true}}})
  expect(wrapper.find('.evidence-metrics').exists()).toBe(false)
  expect(wrapper.text()).toContain('字面重复指标')
  wrapper.unmount()
})
