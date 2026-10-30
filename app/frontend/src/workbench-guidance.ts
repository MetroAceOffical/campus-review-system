import type { Detail, Version, Run } from './api/workbench'
export type DatasetPurpose = 'UNSET' | 'LIBRARY' | 'TRAIN' | 'BOTH'
export const purposeNames: Record<DatasetPurpose, string> = { UNSET: '待选择用途', LIBRARY: '历史新闻库', TRAIN: '模型训练', BOTH: '历史新闻库与模型训练' }
export function purposeFor(kind: string, purpose?: string): DatasetPurpose {
  if (kind === 'PAIRS') return 'TRAIN'
  return ['LIBRARY', 'TRAIN', 'BOTH'].includes(purpose || '') ? purpose as DatasetPurpose : 'UNSET'
}
export function modelVersion(versions: Pick<Version, 'versionId' | 'stage' | 'status'>[], trained?: string): string {
  return versions.find(v => v.versionId === trained && v.stage === 'CLEAN' && v.status === 'READY')?.versionId || ''
}
export async function restoreModelPreparation(detail: Detail, runId: string | undefined, versionId: string, load: (id: string) => Promise<Run>): Promise<Run | undefined> {
  if (!runId || !versionId) return undefined
  const run = detail.runs.find(r => r.runId === runId) || await load(runId)
  if (run.datasetId !== detail.datasetId || run.inputVersionId !== versionId || !['PREPARE','GENERATE'].includes(run.action) || run.status !== 'COMPLETED' || !(run.result as {trainReady?: boolean})?.trainReady) throw new Error('原训练样本划分不可用，请选择其他评价划分。')
  return run
}
export function versionName(v: Version): string {
  const date = v.createdAt ? new Date(v.createdAt.replace(' ', 'T') + (/Z|\+\d\d:\d\d$/.test(v.createdAt) ? '' : 'Z')).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
  return `${v.stage === 'CLEAN' ? '清洗' : '原始'}${date ? ' · ' + date : ''} · ${v.rowCount?.toLocaleString() ?? '待统计'}条 · ${v.versionId.slice(0, 8)}`
}
export interface JourneyStage { key: string; label: string; description: string; status: 'done' | 'active' | 'waiting' | 'error'; icon: string }
export function workflowDestination(detail: Detail, versionId: string, step: string): { path: string; query: Record<string, string> } {
  const version = detail.versions.find(v => v.versionId === versionId)
  const rawId = version?.stage === 'CLEAN' ? version.parentVersionId : versionId
  const clean = version?.stage === 'CLEAN' ? version : detail.versions.find(v => v.stage === 'CLEAN' && v.status === 'READY' && v.parentVersionId === rawId)
  const query: Record<string, string> = { dataset: detail.datasetId, version: clean?.versionId || versionId }
  const trained = detail.runs.find(r => r.action === 'TRAIN' && r.inputVersionId === clean?.versionId && r.status === 'COMPLETED')
  if (step === 'library') {
    const batch = detail.referenceImports?.find(r => r.versionId === clean?.versionId)
    return { path: '/reference-imports', query: { ...query, ...(batch ? { batch: batch.id, tab: 'records' } : { tab: 'new' }) } }
  }
  if (step === 'train' || step === 'prepare') {
    const run = detail.runs.find(r => (step === 'train' ? r.action === 'TRAIN' : ['PREPARE', 'GENERATE'].includes(r.action)) && r.inputVersionId === clean?.versionId)
    return { path: '/training', query: { ...query, ...(run ? { run: run.runId } : { tab: 'new', step: step === 'prepare' ? '1' : '2' }) } }
  }
  if (step === 'evaluate') return { path: '/models', query: { ...query, ...(trained ? { model: trained.runId, tab: 'evaluation' } : {}) } }
  if (step === 'publish') return { path: '/releases', query: { ...query, ...(trained ? { modelId: trained.runId, tab: 'new' } : {}) } }
  return { path: '/datasets', query: { dataset: detail.datasetId, version: ['upload', 'audit'].includes(step) ? rawId || versionId : query.version! } }
}
export function workflowStages(detail: Detail, versionId: string, selectedModel?: string): JourneyStage[] {
  const version = detail.versions.find(v => v.versionId === versionId)
  const sourceId = version?.stage === 'CLEAN' ? version.parentVersionId : versionId
  const clean = version?.stage === 'CLEAN' && version.status === 'READY' ? version : detail.versions.find(v => v.stage === 'CLEAN' && v.status === 'READY' && v.parentVersionId === sourceId)
  const modelId = selectedModel || detail.runs.find(r => r.action === 'TRAIN' && r.inputVersionId === clean?.versionId && r.status === 'COMPLETED')?.runId
  const status = (action: string, input: string | undefined): JourneyStage['status'] => {
    const run = detail.runs.find(r => r.action === action && r.inputVersionId === input && (action !== 'EVALUATE' || r.options?.modelId === modelId))
    return run?.status === 'COMPLETED' ? 'done' : ['QUEUED', 'RUNNING'].includes(run?.status || '') ? 'active' : ['FAILED', 'INTERRUPTED', 'CANCELLED'].includes(run?.status || '') ? 'error' : 'waiting'
  }
  const rows: JourneyStage[] = [
    { key: 'upload', label: '上传数据', description: '保留原始材料', status: 'done', icon: 'upload' },
    { key: 'audit', label: '质量评估', description: '检查缺失与重复', status: clean ? 'done' : status('AUDIT', sourceId), icon: 'search' },
    { key: 'clean', label: '清洗数据', description: '保存可用版本', status: clean ? 'done' : status('CLEAN', sourceId), icon: 'clean' },
  ]
  const purpose = purposeFor(detail.kind, detail.purpose)
  if (purpose === 'LIBRARY' || purpose === 'BOTH') {
    const batch = detail.referenceImports?.find(r => r.versionId === clean?.versionId)
    rows.push({ key: 'library', label: '历史新闻入库', description: batch?.status === 'COMPLETED' ? '已完成入库及索引切换' : batch?.status === 'PENDING_APPROVAL' ? '等待管理员批准' : '准备来源与检索索引', status: batch?.status === 'COMPLETED' ? 'done' : ['FAILED', 'INTERRUPTED', 'WAITING_INDEX'].includes(batch?.status || '') ? 'error' : batch ? 'active' : 'waiting', icon: 'library' })
  }
  if (purpose === 'TRAIN' || purpose === 'BOTH') {
    const ready = detail.runs.find(r => ['PREPARE', 'GENERATE'].includes(r.action) && r.inputVersionId === clean?.versionId && r.status === 'COMPLETED' && (r.result as { trainReady?: boolean })?.trainReady)
    rows.push({ key: 'prepare', label: '准备样本', description: detail.kind === 'NEWS' ? '原稿转为训练句对' : '分组并划分数据', status: ready ? 'done' : status(detail.kind === 'NEWS' ? 'GENERATE' : 'PREPARE', clean?.versionId), icon: 'data' },
      { key: 'train', label: '模型训练', description: '选择模型与参数', status: status('TRAIN', clean?.versionId), icon: 'train' },
      { key: 'evaluate', label: '效果评价', description: '查看测试集表现', status: status('EVALUATE', clean?.versionId), icon: 'model' },
      { key: 'publish', label: '模型发布', description: '在发布页核验使用场景', status: detail.modelReleases?.some(r => r.versionId === clean?.versionId && r.active) ? 'done' : 'waiting', icon: 'release' })
  }
  return rows
}
