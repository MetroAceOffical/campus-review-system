import { describe, expect, it } from 'vitest'
import { normalizeNodeIdentities, moveImage, replaceImage } from '../src/editor/document'
import type { DocumentNode } from '../src/types/document'
import { reactive } from 'vue'

describe('image usage identities', () => {
  it('accepts the reactive document passed by the Vue editor parent', () => {
    const input = reactive<DocumentNode>({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'A😀中' }] }] })
    expect(normalizeNodeIdentities(input).content![0]!.attrs!.nodeId).toBeTruthy()
    expect(input.content![0]!.attrs).toBeUndefined()
  })
  it('allocates a fresh identity for a copied node without changing its file reference', () => {
    const image: DocumentNode = { type: 'campusImage', attrs: { nodeId: 'same', fileId: '42', caption: '图注', origin: 'CITED', sourceUrl: 'https://example.org' } }
    const result = normalizeNodeIdentities({ type: 'doc', content: [structuredClone(image), structuredClone(image)] })
    expect(result.content![0]!.attrs!.nodeId).toBe('same')
    expect(result.content![1]!.attrs!.nodeId).not.toBe('same')
    expect(result.content![1]!.attrs!.fileId).toBe('42')
  })
  it('moves an image with caption and source, while replacement resets its source declaration', () => {
    const result = normalizeNodeIdentities({ type: 'doc', content: [
      { type: 'campusImage', attrs: { nodeId: 'a', fileId: '1', caption: '第一图', origin: 'CITED', sourceUrl: 'https://example.org/a' } },
      { type: 'paragraph', content: [{ type: 'text', text: '正文' }] },
      { type: 'campusImage', attrs: { nodeId: 'b', fileId: '2', caption: '第二图', origin: 'ORIGINAL', sourceUrl: '' } },
    ] })
    const moved = moveImage(result, 'b', -1)
    expect(moved.content![1]!.attrs!.nodeId).toBe('b')
    expect(moved.content![1]!.attrs!.caption).toBe('第二图')
    const replaced = replaceImage(moved, 'a', '3')
    expect(replaced.content![0]!.attrs).toMatchObject({ nodeId: 'a', fileId: '3', caption: '第一图', origin: '', sourceUrl: '' })
  })
})
