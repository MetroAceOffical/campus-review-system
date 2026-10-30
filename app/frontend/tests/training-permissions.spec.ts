import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, it, vi } from 'vitest'
import DatasetJourney from '../src/components/workbench/DatasetJourney.vue'
import type { Detail } from '../src/api/workbench'

const { session } = vi.hoisted(() => ({ session: { user: { role: 'ADMIN' } } }))
vi.mock('../src/session', () => ({ session }))
const dataset = { datasetId: 'news', kind: 'NEWS', purpose: 'BOTH', versions: [{ versionId: 'clean', parentVersionId: 'raw', stage: 'CLEAN', status: 'READY' }], runs: [] } as unknown as Detail
it('keeps the reviewer library flow and exposes training actions only to administrators', () => {
  for (const role of ['ADMIN', 'REVIEWER']) {
    session.user.role = role
    const wrapper = mount(DatasetJourney, { props: { dataset, versionId: 'clean' }, global: { plugins: [ElementPlus], stubs: { RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' } } } })
    expect(wrapper.text()).toContain('查看与继续入库')
    expect(wrapper.text().includes('准备样本与训练')).toBe(role === 'ADMIN')
    const destinations = wrapper.findAllComponents({ name: 'RouterLink' }).map(link => JSON.stringify(link.props('to')))
    expect(destinations.some(to => to.includes('/training'))).toBe(role === 'ADMIN')
    wrapper.unmount()
  }
})
