import { request } from './http'
import type { DocumentInput, SavedDraft } from '../types/document'
export interface Page<T> { items: T[]; page: number; pageSize: number; total: number }
export interface Manuscript { manuscriptId: string; title: string; status: string; publicationState: string; organizationName: string; currentSubmissionId: string | null; updatedAt: string }
export interface Version { submissionId: string; versionNo: number; title: string; lifecycleStatus: string; submittedAt: string; batchId: string | null; decision: string; reason: string }
export interface Snapshot extends DocumentInput { submissionId: string; manuscriptId: string; versionNo: number; lifecycleStatus: string; submittedAt: string; plainText?: string; positionMap?: import('../editor/positions').PositionMap[]; decision: { decisionId: string; decision: string; reason: string; decidedAt: string } | null }
export interface Progress { batchId: string; status: string; completedItems: number; totalItems: number; items: Array<{ itemId: string; type: string; targetKey: string; status: string; activeAttemptId: string | null }> }
export const stateLabel: Record<string, string> = { DRAFT: '草稿', PENDING: '待审', RETURNED: '退回', APPROVED: '通过', REJECTED: '拒绝', QUEUED: '排队中', WAITING_SERVICE: '等待服务', RUNNING: '处理中', COMPLETED: '已完成', PARTIAL_FAILED: '部分失败', FAILED: '失败', INTERRUPTED: '已中断', NOT_APPLICABLE: '不适用', CANCELLED: '已取消' }
export const decisionLabel: Record<string, string> = { APPROVE: '通过', RETURN: '退回', REJECT: '拒绝' }
export const listManuscripts = (page: number, q: string, status: string) => request<Page<Manuscript>>(`/api/manuscripts?${new URLSearchParams({ page: String(page), q, status })}`)
export const saveDraft = (id: string, revision: string, input: DocumentInput) => request<SavedDraft>(`/api/manuscripts/${id}/draft`, { method: 'PUT', body: JSON.stringify({ ...input, expectedRevision: revision }) })
export const submitDraft = (id: string, key: string, revision: string, input: DocumentInput) => request<{ submissionId: string; versionNo: number; batchId: string; draftRevision: string }>(`/api/manuscripts/${id}/submissions`, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ ...input, expectedDraftRevision: revision }) })
export const getSubmissions = (id: string) => request<{ manuscriptId: string; status: string; items: Version[] }>(`/api/manuscripts/${id}/submissions`)
export const getSubmission = (id: string) => request<Snapshot>(`/api/submissions/${id}`)
export const getProgress = (id: string) => request<Progress>(`/api/detection-batches/${id}/progress`)
