import { Extension, Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import { Plugin } from '@tiptap/pm/state'
import type { Editor } from '@tiptap/core'
import CampusImageView from '../components/CampusImageView.vue'

export function insertUploadedImage(editor: Editor, fileId: string) {
  return editor.chain().focus().insertContentAt(editor.state.selection.to, { type: 'campusImage', attrs: { nodeId: crypto.randomUUID(), fileId, caption: '', origin: '', sourceUrl: '' } }).run()
}

export const CampusImage = Node.create({
  name: 'campusImage', group: 'block', atom: true, draggable: true,
  addAttributes() { return { nodeId: { default: null }, fileId: { default: null }, caption: { default: '' }, origin: { default: '' }, sourceUrl: { default: '' } } },
  parseHTML() { return [{ tag: 'figure[data-campus-image]' }] },
  renderHTML({ HTMLAttributes }) { return ['figure', mergeAttributes({ 'data-campus-image': '' }, HTMLAttributes), ['img', { src: `/api/files/${HTMLAttributes.fileId}`, alt: HTMLAttributes.caption }], ['figcaption', {}, HTMLAttributes.caption || '']] },
  addNodeView() { return VueNodeViewRenderer(CampusImageView) },
})

export const StableNodeIdentities = Extension.create({
  name: 'stableNodeIdentities',
  addGlobalAttributes() { return [{ types: ['paragraph', 'heading'], attributes: { nodeId: { default: null, parseHTML: element => element.getAttribute('data-node-id'), renderHTML: attrs => attrs.nodeId ? { 'data-node-id': attrs.nodeId } : {} } } }] },
  addProseMirrorPlugins() {
    return [new Plugin({ appendTransaction(transactions, old, state) {
      if (!transactions.some(transaction => transaction.docChanged)) return null
      const retained = new Map<string, number>()
      old.doc.descendants((node, position) => {
        const id = node.attrs.nodeId
        if (typeof id !== 'string' || !id) return
        const mapped = transactions.reduce((current, transaction) => transaction.mapping.map(current, 1), position)
        if (state.doc.nodeAt(mapped)?.attrs.nodeId === id) retained.set(id, mapped)
      })
      const seen = new Set<string>(), transaction = state.tr
      state.doc.descendants((node, position) => {
        if (!['paragraph', 'heading', 'campusImage'].includes(node.type.name)) return
        let id = node.attrs.nodeId
        if (typeof id !== 'string' || !id || seen.has(id) || (retained.has(id) && retained.get(id) !== position)) { id = crypto.randomUUID(); transaction.setNodeMarkup(position, undefined, { ...node.attrs, nodeId: id }) }
        seen.add(id)
      })
      return transaction.docChanged ? transaction : null
    } })]
  },
})
