export interface DocumentNode { type: string; attrs?: Record<string, string | number | null>; text?: string; marks?: Array<{ type: string; attrs?: Record<string, unknown> }>; content?: DocumentNode[] }
export interface Source { sourceId: string; url: string; kind?: 'INTERNAL' | 'EXTERNAL'; workId?: string; revisionId?: string; title?: string }
export interface DocumentInput { title: string; schemaVersion: '1' | '2'; content: DocumentNode; sources: Source[] }
export interface SavedDraft extends DocumentInput { manuscriptId: string; organizationId: string; status: string; revision: string; savedAt: string }
export interface UploadedFile { fileId: string; mimeType: string; width: number; height: number; sizeBytes: number }
