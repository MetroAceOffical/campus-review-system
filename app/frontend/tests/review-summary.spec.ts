import { expect,it } from 'vitest'
import { summarizeEvidence,highlightText } from '../src/review-summary'
import type { TextEvidenceItem } from '../src/api/review'
it('shows semantic evidence, deduplicates ranges and preserves cited status without literal zeros',()=>{
  const item:TextEvidenceItem={evidenceType:'TEXT_SIMILARITY',sourceKind:'BODY',tfidfScore:.4,evidenceId:'e1',sourceWorkId:'1',sourceRevisionId:'2',sourceTitle:'原稿',fullyCited:false,acceptedCandidate:false,literalSummary:{matched_characters:0,query_character_coverage:0,longest_match:0},semanticSummary:{status:'EVALUATED',suspectedReuse:true,supportingPairs:2,matchedQueryCharacters:80},semanticWindows:[{queryStart:0,queryEnd:40,sourceStart:0,sourceEnd:40,queryText:'',sourceText:'',score:.8,citationSupport:true},{queryStart:40,queryEnd:80,sourceStart:40,sourceEnd:80,queryText:'',sourceText:'',score:.9,citationSupport:true}],matches:[]}
  const result=summarizeEvidence(item,100)
  expect(result.verdict).toBe('疑似复用');expect(result.metrics.map(m=>m.label)).not.toContain('字面重复字符')
  expect(result.metrics.some(m=>m.value==='80')).toBe(true)
  expect(summarizeEvidence({...item,fullyCited:true},100).verdict).toBe('已标注引用')
  expect(highlightText('甲😀乙',[{start:1,end:2}])).toEqual([{text:'甲',marked:false},{text:'😀',marked:true},{text:'乙',marked:false}])
})
