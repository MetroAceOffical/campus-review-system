import { Mark, mergeAttributes } from '@tiptap/core'
export const Citation = Mark.create({
  name: 'citation', inclusive: false,
  addAttributes() { return { sourceIds: { default: [], parseHTML: element => { try { const value = JSON.parse(element.getAttribute('data-citation-ids') ?? '[]'); return Array.isArray(value) ? value.filter(v => typeof v === 'string').slice(0, 16) : [] } catch { return [] } }, renderHTML: attributes => ({ 'data-citation-ids': JSON.stringify(attributes.sourceIds) }) } } },
  parseHTML() { return [{ tag: 'span[data-citation-ids]' }] },
  renderHTML({ HTMLAttributes }) { return ['span', mergeAttributes(HTMLAttributes, { class: 'citation-text', title: '已添加片段来源' }), 0] },
})
