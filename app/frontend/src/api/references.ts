import { request } from './http'
import type { DocumentInput } from '../types/document'
import type { Page } from './manuscripts'
import type { RecognitionResult } from './review'
export interface ReferencePart { status: string; errorCode?: string; result?: RecognitionResult }
export interface ReferenceMetadata { sourceType: string; url?: string; description?: string; sourceOrganization?: string; published_at?: string; published_at_local?: string; imageSources?: Array<{ importStatus?: string; errorCode?: string }> }
export interface Reference { referenceId: string; revisionId: string; title: string; originType: string; requestedEnabled: boolean; effectiveEnabled: boolean; processingStatus: string; sourceMetadata: ReferenceMetadata; parts: Record<string, ReferencePart>; imageNumbers?: Record<string, number>; createdAt: string; createdByName: string; originalPublishedAt: string | null }
export interface ReferencePage extends Page<Reference> { activeGenerationId: string | null; latestGeneration: { generationId: string; status: string } | null }
export interface ReferenceSnapshot extends DocumentInput { referenceId: string; revisionId: string; sourceMetadata: ReferenceMetadata }
export interface PublicationSummary { manuscriptId: string; submissionId: string; title: string; organizationName: string; publishedAt: string }
export interface Publication extends DocumentInput, PublicationSummary { reprintAllowed: boolean }
export const referenceLabel: Record<string, string> = { QUEUED: '排队中', PROCESSING: '处理中', PREPARED: '等待索引切换', READY: '可用于比对', PARTIAL: '部分可用', FAILED: '处理失败', AVAILABLE: '可用', NOT_APPLICABLE: '不适用', PENDING_INDEX: '等待索引' }
export const listReferences = (page: number, q: string) => request<ReferencePage>(`/api/references?${new URLSearchParams({ page: String(page), q })}`)
export const getReference = (id: string) => request<ReferenceSnapshot>(`/api/references/${id}`)
export const createReference = (key: string, input: DocumentInput & { sourceMetadata: ReferenceMetadata }) => request<{ referenceId: string }>(`/api/references`, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(input) })
export const setReferenceEnabled = (id: string, key: string, enabled: boolean) => request<{ requestedEnabled: boolean; effectiveEnabled: boolean; status: string }>(`/api/references/${id}/enabled`, { method: 'PATCH', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ enabled }) })
export const retryReference = (id: string, key: string, failedPartKeys: string[] = []) => request(`/api/references/${id}/retries`, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ failedPartKeys }) })
export const listPublications = (page: number, q: string) => request<Page<PublicationSummary>>(`/api/publications?${new URLSearchParams({ page: String(page), q })}`)
export const getPublication = (id: string) => request<Publication>(`/api/publications/${id}`)
