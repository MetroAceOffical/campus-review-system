import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { expect, it } from 'vitest'
import { CampusImage, StableNodeIdentities, insertUploadedImage } from '../src/editor/CampusImage'

it('a new upload inserts after a selected image without overwriting its caption and source', () => {
  const editor = new Editor({ element: document.createElement('div'), extensions: [StarterKit, CampusImage, StableNodeIdentities], content: {
    type: 'doc', content: [{ type: 'campusImage', attrs: { nodeId: 'first', fileId: '42', caption: '保留图注', origin: 'CITED', sourceUrl: 'https://example.org/first' } }, { type: 'paragraph' }],
  } })
  try {
    editor.commands.setNodeSelection(0)
    insertUploadedImage(editor, '43')
    const nodes = editor.getJSON().content!.filter(node => node.type === 'campusImage')
    expect(nodes).toHaveLength(2)
    expect(nodes[0]!.attrs).toMatchObject({ nodeId: 'first', fileId: '42', caption: '保留图注', sourceUrl: 'https://example.org/first' })
    expect(nodes[1]!.attrs!.fileId).toBe('43')
  } finally { editor.destroy() }
})

it('pasting a copy before the original preserves the original usage identity', () => {
  const editor = new Editor({ element: document.createElement('div'), extensions: [StarterKit, CampusImage, StableNodeIdentities], content: {
    type: 'doc', content: [{ type: 'campusImage', attrs: { nodeId: 'original', fileId: '42', caption: '原图图注', origin: 'ORIGINAL', sourceUrl: '' } }, { type: 'paragraph' }],
  } })
  try {
    const original = editor.state.doc.firstChild!
    editor.view.dispatch(editor.state.tr.insert(0, original))
    const nodes = editor.getJSON().content!.filter(node => node.type === 'campusImage')
    expect(nodes[0]!.attrs!.nodeId).not.toBe('original')
    expect(nodes[1]!.attrs!.nodeId).toBe('original')
    expect(nodes[0]!.attrs!.fileId).toBe('42')
  } finally { editor.destroy() }
})
