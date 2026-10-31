import { request } from './http'
export interface Audit {
  totalRows: number; validRows: number; invalidRows: number; duplicateRows: number
  missing: Record<string, number>; completeness: Record<string, number>; issueCounts: Record<string, number>
  lengths: Record<string, { histogram: Array<{ length: number; count: number }> }>
  sourceDistribution: Record<string, number>; departmentDistribution: Record<string, number>
  dateDistribution: Record<string, number>; classDistribution: Record<string, number>
}
export interface Dataset { datasetId: string; organizationId: string; name: string; kind: 'NEWS' | 'PAIRS'; archived: boolean; catalog?:'USER'|'FORMAL'|'HISTORY';purpose?: 'UNSET' | 'LIBRARY' | 'TRAIN' | 'BOTH' }
export interface Version { versionId: string; stage: 'RAW' | 'CLEAN'; status: string; sha256: string; rowCount: number | null; origin?: 'COMPOSITION'; createdAt?: string; parentVersionId?: string }
export interface RunResult { audit?: Audit; columns?: string[]; mapping?: Record<string, string>; preview?: Array<Record<string, unknown>>; outputRows?: number; quarantineRows?: number; duplicateRows?: number }
export interface Run { runId: string; datasetId: string; inputVersionId: string; outputVersionId: string; action: string; status: string; error: string; result?: RunResult; options?: { modelId?: string }; mapping?: Record<string, string>; createdAt?: string }
export interface Detail extends Dataset { versions: Version[]; runs: Run[]; referenceImports?: Array<{ id: string; versionId: string; status: string; generationId?: string }>; modelReleases?: Array<{id: string;versionId: string;status: string;active: boolean | number}> }
export interface Progress { sequence: number; data: { stage: string; processed?: number; total?: number; retained?: number; quarantined?: number; duplicates?: number; message?: string } }
export interface Cleaning { before: Audit; after: Audit; inputRows: number; outputRows: number; duplicateRows: number }
export interface Page<T> { items: T[]; total: number }
export const organizations = () => request<Array<{ organizationId: string; name: string }>>('/api/workbench/organizations')
export const datasets = (page: number, q: string, archived: boolean, pageSize = 12,history=false) => request<Page<Dataset>>(`/api/workbench/datasets?page=${page}&pageSize=${pageSize}&q=${encodeURIComponent(q)}&archived=${archived}&history=${history}`)
export const dataset = (id: string) => request<Detail>(`/api/workbench/datasets/${id}`)
export const upload = (form: FormData) => request<{ datasetId: string; versionId: string; runId: string }>('/api/workbench/datasets', { method: 'POST', body: form })
export const update = (id: string, fields: { name?: string; archived?: boolean; purpose?: string }) => request<Detail>(`/api/workbench/datasets/${id}`, { method: 'PATCH', body: JSON.stringify(fields) })
export const start = (id: string, versionId: string, action: string, mapping: Record<string, string>, options: Record<string, unknown>) => request<{ runId: string }>(`/api/workbench/datasets/${id}/runs`, { method: 'POST', body: JSON.stringify({ versionId, action, mapping, options }) })
export const run = (id: string) => request<Run>(`/api/workbench/runs/${id}`)
export const events = (id: string, after = 0) => request<Progress[]>(`/api/workbench/runs/${id}/events?after=${after}`)
export const cancel = (id: string) => request<Run>(`/api/workbench/runs/${id}/cancel`, { method: 'POST' })
export const report = (id: string, version: string) => request<Cleaning>(`/api/workbench/datasets/${id}/versions/${version}/report`)
export const rows = (id: string, version: string, page: number, pageSize = 10) => request<Page<Record<string, unknown>>>(`/api/workbench/datasets/${id}/versions/${version}/rows?page=${page}&pageSize=${pageSize}`)
export const downloadUrl = (id: string, version: string, artifact: string) => `/api/workbench/datasets/${id}/versions/${version}/files/${encodeURIComponent(artifact)}`
export interface Composition { sources: Array<{ datasetId: string; versionId: string; name: string; inputRows: number; retainedRows: number; duplicateRows: number; quarantineRows: number }>; inputRows: number; outputRows: number; duplicateRows: number; quarantineRows: number }
export const compose = (organizationId: string, name: string, sources: Array<{ datasetId: string; versionId: string }>) => request<{ datasetId: string; versionId: string; runId: string }>('/api/workbench/datasets/compose', { method: 'POST', body: JSON.stringify({ organizationId, name, sources }) })
export const composition = (id: string, version: string) => request<Composition>(`/api/workbench/datasets/${id}/versions/${version}/composition`)

export const datasetRuns=(id:string,page=1,pageSize=20)=>request<Page<Run>>(`/api/workbench/datasets/${id}/runs?page=${page}&pageSize=${pageSize}`)
