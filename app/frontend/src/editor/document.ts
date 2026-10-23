import type { DocumentNode } from '../types/document'
const copyDocument = (input: DocumentNode): DocumentNode => JSON.parse(JSON.stringify(input))

export function normalizeNodeIdentities(input: DocumentNode): DocumentNode {
  const document = copyDocument(input), seen = new Set<string>()
  function walk(node: DocumentNode) {
    if (['paragraph', 'heading', 'campusImage'].includes(node.type)) {
      const attrs = node.attrs ??= {}
      const id = attrs.nodeId
      if (typeof id !== 'string' || !id || seen.has(id)) attrs.nodeId = crypto.randomUUID()
      seen.add(attrs.nodeId as string)
    }
    node.content?.forEach(walk)
  }
  walk(document)
  return document
}
export function moveImage(input: DocumentNode, nodeId: string, direction: -1 | 1): DocumentNode {
  const document = copyDocument(input)
  function walk(parent: DocumentNode): boolean {
    const children = parent.content
    if (!children) return false
    const index = children.findIndex(node => node.type === 'campusImage' && node.attrs?.nodeId === nodeId)
    if (index >= 0) {
      const target = index + direction
      if (target >= 0 && target < children.length) [children[index], children[target]] = [children[target]!, children[index]!]
      return true
    }
    return children.some(walk)
  }
  walk(document)
  return document
}
export function replaceImage(input: DocumentNode, nodeId: string, fileId: string): DocumentNode {
  const document = copyDocument(input)
  function walk(node: DocumentNode) {
    if (node.type === 'campusImage' && node.attrs?.nodeId === nodeId) node.attrs = { ...node.attrs, fileId, origin: '', sourceUrl: '' }
    node.content?.forEach(walk)
  }
  walk(document)
  return document
}
