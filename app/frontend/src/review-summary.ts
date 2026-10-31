import type { TextEvidenceItem } from './api/review'
export interface EvidencePair {queryStart:number;queryEnd:number;sourceStart?:number;sourceEnd?:number;queryText:string;sourceText:string;score?:number;kind:string;supported?:boolean}
function supportingWindows(item:TextEvidenceItem){
  if(item.semanticWindows.some(w=>w.citationSupport!==undefined))return item.semanticWindows.filter(w=>w.citationSupport)
  const summary=item.semanticSummary,selected:TextEvidenceItem['semanticWindows']=[]
  if(summary?.scoreThreshold===undefined||summary.lexicalFloor===undefined)return selected
  for(const w of [...item.semanticWindows].sort((a,b)=>b.score-a.score||(b.tfidfScore||0)-(a.tfidfScore||0)||a.queryStart-b.queryStart)){
    if(w.score<summary.scoreThreshold||(w.tfidfScore||0)<summary.lexicalFloor||w.queryEnd-w.queryStart<12||w.sourceStart===undefined||w.sourceEnd===undefined)continue
    if(!selected.some(p=>w.queryStart<p.queryEnd&&p.queryStart<w.queryEnd||w.sourceStart!<p.sourceEnd!&&p.sourceStart!<w.sourceEnd!))selected.push(w)
  }
  return selected
}
export function evidencePairs(item:TextEvidenceItem):EvidencePair[]{
  const seen=new Set<string>(),rows:EvidencePair[]=[]
  const support=supportingWindows(item),windows=support.length?support:item.semanticWindows
  for(const row of [...item.matches.map(m=>({...m,kind:'字面重复',supported:true})),...windows.map(w=>({...w,supported:support.includes(w),kind:support.includes(w)?'语义复用证据':'语义对照'}))]){
    const queryStart=row.queryStart+Array.from(row.queryText.match(/^\s*/u)?.[0]||'').length,sourceStart=row.sourceStart===undefined?'':row.sourceStart+Array.from(row.sourceText.match(/^\s*/u)?.[0]||'').length
    const key=[queryStart,sourceStart,row.queryText.trim(),row.sourceText.trim()].join('|')
    if(!seen.has(key)){seen.add(key);rows.push(row)}
  }
  return rows.sort((a,b)=>a.queryStart-b.queryStart||(b.score||0)-(a.score||0))
}
export function summarizeEvidence(item:TextEvidenceItem,totalCharacters:number){
  const semantic=!!item.semanticSummary?.suspectedReuse,literal=!!(item.literalAcceptedCandidate??item.acceptedCandidate),cited=!!item.fullyCited
  const metrics:Array<{label:string;value:string;unit?:string}>=[]
  if(semantic&&item.semanticSummary){
    const s=item.semanticSummary
    if(s.supportingPairs>0)metrics.push({label:cited?'引用对应片段':'支持复用片段',value:String(s.supportingPairs),unit:'组'})
    if(s.matchedQueryCharacters>0){metrics.push({label:'涉及本稿文字',value:String(s.matchedQueryCharacters),unit:'字'});if(totalCharacters>0)metrics.push({label:'本稿证据覆盖',value:(Math.min(1,s.matchedQueryCharacters/totalCharacters)*100).toFixed(1),unit:'%'})}
    const scores=supportingWindows(item).map(w=>w.score)
    if(scores.length)metrics.push({label:'最高片段得分',value:Math.max(...scores).toFixed(3)})
  }else if(literal&&item.literalSummary.matched_characters>0){
    metrics.push({label:'重复文字',value:String(item.literalSummary.matched_characters),unit:'字'})
    if(item.literalSummary.query_character_coverage>0)metrics.push({label:'本稿重复覆盖',value:(item.literalSummary.query_character_coverage*100).toFixed(1),unit:'%'})
    if(item.literalSummary.longest_match>0)metrics.push({label:'最长重复片段',value:String(item.literalSummary.longest_match),unit:'字'})
  }
  return{verdict:cited?'已标注引用':semantic||literal?'疑似复用':'相近片段',warning:!cited&&(semantic||literal),metrics}
}
export function highlightText(text:string,ranges:Array<{start:number;end:number}>){
  const chars=Array.from(text),valid=ranges.filter(r=>Number.isInteger(r.start)&&Number.isInteger(r.end)&&r.start>=0&&r.end>r.start&&r.end<=chars.length)
  const cuts=[...new Set([0,chars.length,...valid.flatMap(r=>[r.start,r.end])])].sort((a,b)=>a-b)
  return cuts.slice(0,-1).map((start,i)=>({text:chars.slice(start,cuts[i+1]).join(''),marked:valid.some(r=>r.start<cuts[i+1]!&&r.end>start)}))
}
