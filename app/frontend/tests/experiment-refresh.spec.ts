import { describe,it,expect,vi } from 'vitest'
import { createExperimentState } from '../src/api/experiments'

describe('frozen experiment refresh',()=>{
  it('keeps chart identity when unchanged or refresh fails, replaces only a complete new bundle',async()=>{
    const first={manifest:{id:'test',contentVersion:'one'},lastCheckedAt:'first'}
    const fetcher=vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce({...first,lastCheckedAt:'second'}).mockRejectedValueOnce(new Error('包损坏')).mockResolvedValueOnce({...first,manifest:{id:'test',contentVersion:'two'},lastCheckedAt:'third'})
    const state=createExperimentState(fetcher)
    await state.refresh('test');const saved=state.bundle.value
    await state.refresh('test');expect(state.bundle.value).toBe(saved);expect(state.checkedAt.value).toBe('second')
    await state.refresh('test');expect(state.bundle.value).toBe(saved);expect(state.error.value).toContain('包损坏')
    await state.refresh('test');expect(state.bundle.value?.manifest.contentVersion).toBe('two');expect(state.error.value).toBe('')
  })
  it('does not let an older response overwrite the selected experiment',async()=>{
    let resolve!:(value:unknown)=>void
    const fetcher=vi.fn().mockImplementationOnce(()=>new Promise(done=>resolve=done)).mockResolvedValueOnce({manifest:{id:'b',contentVersion:'b'},lastCheckedAt:'now'})
    const state=createExperimentState(fetcher)
    const older=state.refresh('a');await state.refresh('b');resolve({manifest:{id:'a',contentVersion:'a'},lastCheckedAt:'old'});await older
    expect(state.bundle.value?.manifest.id).toBe('b')
  })
})
