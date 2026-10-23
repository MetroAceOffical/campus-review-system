import { shallowRef } from 'vue'
import { request } from '../api/http'
import type { DocumentInput,DocumentNode } from '../types/document'
export interface Limits {titleCodePoints:number;bodyCodePoints:number;images:number;imageBytes:number;imagePixels:number;imageSide:number;urlCharacters:number}
export const limits=shallowRef<Limits>()
let pending:Promise<Limits>|undefined
export async function loadLimits(){
  if(limits.value)return limits.value
  if(!pending)pending=request<Limits>('/api/settings/limits').then(value=>{for(const key of ['titleCodePoints','bodyCodePoints','images','imageBytes','imagePixels','imageSide','urlCharacters'] as const)if(!Number.isSafeInteger(value[key])||value[key]<=0)throw new Error('输入限额配置不可用');limits.value=value;return value}).finally(()=>pending=undefined)
  return pending
}
export function documentSize(input:DocumentInput){
  let images=0;const blocks:string[]=[]
  function walk(node:DocumentNode){if(node.type==='campusImage'){images++;return}if(['paragraph','heading'].includes(node.type)){blocks.push((node.content??[]).map(child=>child.type==='hardBreak'?'\n':(child.text??'').replace(/\r\n?/g,'\n')).join(''));return}node.content?.forEach(walk)}
  walk(input.content);return {title:Array.from(input.title).length,body:Array.from(blocks.join('\n')).length,images}
}
export function validationMessage(input:DocumentInput,config:Limits|undefined){
  if(!config)return '输入限额尚未读取，请稍后重试'
  const size=documentSize(input)
  if(size.title>config.titleCodePoints)return `标题最多${config.titleCodePoints}个Unicode字符，当前${size.title}个；内容已保留`
  if(size.body>config.bodyCodePoints)return `正文最多${config.bodyCodePoints}个Unicode字符，当前${size.body}个；内容已保留`
  if(size.images>config.images)return `每稿最多${config.images}张配图；当前配图已保留，请移除超出部分`
  let urlTooLong=input.sources.some(source=>source.url.length>config.urlCharacters)
  function urls(node:DocumentNode){if(typeof node.attrs?.sourceUrl==='string'&&node.attrs.sourceUrl.length>config!.urlCharacters)urlTooLong=true;node.content?.forEach(urls)}urls(input.content)
  return urlTooLong?`来源链接最多${config.urlCharacters}字符；输入已保留`:''
}
