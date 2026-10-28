import { request } from './http'
import type { Run, Page } from './workbench'
export const modelNames: Record<string, string> = { lr: '逻辑回归 LR', svm: '支持向量机 SVM', rf: '随机森林 RF', cnn: '卷积网络 CNN', bilstm: '双向 LSTM', bert: '中文 BERT' }
export interface Metrics { rows: number; accuracy: number; precision: number; recall: number; f1: number; macro_f1: number; roc_auc: number | null; average_precision: number | null; confusionMatrix: number[][]; roc: number[][]; pr: number[][] }
export interface Preparation { trainReady: boolean; requiresLabels: boolean; inputRows: number; groups: number; segments: number; missingClassPartitions: string[]; partitions: Record<string, { rows: number; groups: number; labels: Record<string, number> }>; groupSizeDistribution: Record<string, number> }
export interface ModelManifest { trainRows: number; validationRows: number; family: string; validation: Metrics; parameters: Record<string, unknown>; elapsedSeconds: number; bestEpoch: number | null; iterations: number | null; converged: boolean; reloadMaxDifference: number }
export interface Prediction { id: string; sentence1: string; sentence2: string; score: number; predicted: number; label?: number; scoreType: string }
export interface ComputeRun extends Omit<Run, 'result'> { datasetName?: string; options: { family?: string; name?: string; preparationId?: string; modelId?: string; parameters?: Record<string, unknown> }; result?: Partial<Preparation & ModelManifest> & { metrics?: Metrics; count?: number; rows?: Prediction[] } }
export interface Model { modelId: string; organizationId: string; datasetId: string; runId: string; name: string; family: string; archived: boolean; createdAt: string; manifest: ModelManifest }
export interface ComputeEvent { sequence: number; data: { stage: string; processed?: number; total?: number; epoch?: number; epochs?: number; step?: number; steps?: number; loss?: number; learningRate?: number; trees?: number; elapsedSeconds?: number; message?: string; validation?: Metrics } }
export const runs = (page = 1, q = '') => request<Page<ComputeRun>>(`/api/workbench/training/runs?page=${page}&q=${encodeURIComponent(q)}`)
export const run = (id: string) => request<ComputeRun>(`/api/workbench/runs/${id}`)
export const events = (id: string, after = 0) => request<ComputeEvent[]>(`/api/workbench/runs/${id}/events?after=${after}`)
export const start = (body: Record<string, unknown>) => request<{ runId: string }>('/api/workbench/training/runs', { method: 'POST', body: JSON.stringify(body) })
export const models = (page = 1, q = '', archived = false) => request<Page<Model>>(`/api/workbench/training/models?page=${page}&q=${encodeURIComponent(q)}&archived=${archived}`)
export const updateModel = (id: string, fields: { name?: string; archived?: boolean }) => request<Model>(`/api/workbench/training/models/${id}`, { method: 'PATCH', body: JSON.stringify(fields) })
export const artifact = (id: string, name: string) => `/api/workbench/training/runs/${id}/files/${name}`
export const terminal = (status: string) => ['COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'].includes(status)
export const stateNames: Record<string, string> = { QUEUED: '排队中', RUNNING: '运行中', COMPLETED: '已完成', FAILED: '失败', CANCELLED: '已取消', INTERRUPTED: '已中断', RESOURCE_CHECK: '检查资源', WAITING_RESOURCE: '等待资源', GROUPING: '来源分组', SPLITTING: '数据划分', PREPARED: '样本已保存', FEATURES: '特征与编码', TRAINING: '训练中', EPOCH: '验证完成', VALIDATED: '验证完成', MODEL_SAVED: '模型已保存', PREDICTING: '预测中', HEARTBEAT: '计算中' }
export const actionNames: Record<string, string> = { PREPARE: '样本准备', TRAIN: '模型训练', EVALUATE: '独立评估', PREDICT: '模型预测' }
