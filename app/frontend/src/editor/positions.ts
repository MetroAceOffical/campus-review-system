import type { DocumentNode } from '../types/document'
export interface PositionMap { nodeId: string; plainStart: number; plainEnd: number; nodeTextStart: number; nodeTextEnd: number }
export interface EditorRange { nodeId: string; from: number; to: number; nodeFrom: number; nodeTo: number }
export function codePointRangeToEditorRange(document: DocumentNode, map: PositionMap[], start: number, end: number): EditorRange[] {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) throw new Error('无效的正文范围')
  const nodes = new Map<string, { position: number; text: string }>()
  function walk(node: DocumentNode, position: number): number {
    if (node.type === 'text') return node.text?.length ?? 0
    if (node.type === 'hardBreak' || node.type === 'campusImage') return 1
    if (['paragraph', 'heading'].includes(node.type)) nodes.set(String(node.attrs?.nodeId), { position: position + 1, text: node.content?.map(child => child.type === 'hardBreak' ? '\n' : child.text ?? '').join('') ?? '' })
    let size = 0
    for (const child of node.content ?? []) size += walk(child, position + (node.type === 'doc' ? 0 : 1) + size)
    return node.type === 'doc' ? size : size + 2
  }
  walk(document, 0)
  const result: EditorRange[] = []
  for (const entry of map) {
    const from = Math.max(start, entry.plainStart), to = Math.min(end, entry.plainEnd)
    if (from >= to) continue
    const node = nodes.get(entry.nodeId)
    if (!node) throw new Error('报告位置与送审快照不一致')
    const nodeFrom = Array.from(node.text).slice(0, entry.nodeTextStart + from - entry.plainStart).join('').length
    const nodeTo = Array.from(node.text).slice(0, entry.nodeTextStart + to - entry.plainStart).join('').length
    const previous = result[result.length - 1]
    if (previous?.nodeId === entry.nodeId && previous.to === node.position + nodeFrom) { previous.to = node.position + nodeTo; previous.nodeTo = nodeTo }
    else result.push({ nodeId: entry.nodeId, from: node.position + nodeFrom, to: node.position + nodeTo, nodeFrom, nodeTo })
  }
  return result
}
