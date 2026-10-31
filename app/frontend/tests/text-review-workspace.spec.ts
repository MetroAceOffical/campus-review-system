import {mount,flushPromises} from '@vue/test-utils'
import ElementPlus from 'element-plus'
import {expect,it,vi} from 'vitest'
import TextReviewWorkspace from '../src/components/TextReviewWorkspace.vue'
import type {TextEvidenceItem} from '../src/api/review'
vi.mock('../src/api/review',()=>({evidenceSource:vi.fn(async()=>({title:'来源海报',plainText:'校园新闻'.repeat(30),sourceRevisionId:'10',sourceWorkId:'1',sourceKind:'IMAGE_OCR',url:'',libraryGenerationId:'1'}))}))
it('counts one work across revisions and retains OCR image evidence in full-text review',async()=>{
  const item:TextEvidenceItem={evidenceId:'ocr',evidenceType:'TEXT_SIMILARITY',sourceWorkId:'1',sourceRevisionId:'10',sourceTitle:'校园新闻',sourceKind:'IMAGE_OCR',tfidfScore:.4,acceptedCandidate:false,literalSummary:{matched_characters:0,query_character_coverage:0,longest_match:0},matches:[],semanticWindows:[],semanticSummary:{status:'EVALUATED',suspectedReuse:true,supportingPairs:2,matchedQueryCharacters:80},sourceMetadata:{sourceFileId:'image',ocr:{recognitionLines:[],combinedText:'校园新闻'}}}
  const wrapper=mount(TextReviewWorkspace,{props:{document:{title:'本稿',schemaVersion:'1',content:{type:'doc',content:[{type:'paragraph',attrs:{nodeId:'p'},content:[{type:'text',text:'校园新闻'.repeat(30)}]}]},sources:[]},evidence:[item,{...item,evidenceId:'body',sourceRevisionId:'11',sourceKind:'BODY'}],check:'check'},global:{plugins:[ElementPlus],stubs:{ReadOnlyDocument:true,OcrEvidence:true,RecordPagination:true}}})
  await flushPromises();expect(wrapper.text()).toContain('1个来源存在有效复用证据');expect(wrapper.text()).toContain('来源图片文字');expect(wrapper.find('ocr-evidence-stub').exists()).toBe(true);expect(wrapper.find('.verdict-metrics').text()).not.toContain('字面重复');wrapper.unmount()
})
