import { expect, test } from 'vitest'
import { purposeFor, modelVersion, workflowStages, restoreModelPreparation } from '../src/workbench-guidance'

test('news purposes remain selectable and pairs cannot enter the article library', () => {
  expect(purposeFor('NEWS', 'BOTH')).toBe('BOTH')
  expect(purposeFor('PAIRS', 'BOTH')).toBe('TRAIN')
  expect(purposeFor('NEWS', undefined)).toBe('UNSET')
})

test('fetches original preparation even when outside the latest dataset tasks', async () => {
  const original = { runId:'old', datasetId:'dataset', inputVersionId:'trained', action:'PREPARE', status:'COMPLETED', result:{trainReady:true} }
  const detail = {datasetId:'dataset',runs:[]} as any
  expect(await restoreModelPreparation(detail,'old','trained',async () => original as any)).toEqual(original)
  await expect(restoreModelPreparation(detail,'old','trained',async () => ({...original,datasetId:'other'}) as any)).rejects.toThrow('原训练样本划分')
})

test('restores exact trained input instead of the latest version and explains missing inputs', () => {
  const versions = [{ versionId: 'latest', stage: 'CLEAN' as const, status: 'READY' }, { versionId: 'trained', stage: 'CLEAN' as const, status: 'READY' }]
  expect(modelVersion(versions, 'trained')).toBe('trained')
  expect(modelVersion(versions, 'missing')).toBe('')
})

test('a training result is not a completed library import or a model publication', () => {
  const detail = { kind: 'NEWS', purpose: 'BOTH', versions: [{ versionId: 'clean', stage: 'CLEAN', status: 'READY' }], runs: [{ action: 'TRAIN', status: 'COMPLETED', inputVersionId: 'clean' }], referenceImports: [] }
  const stages = workflowStages(detail as any, 'clean')
  expect(stages.find(s => s.key === 'train')?.status).toBe('done')
  expect(stages.find(s => s.key === 'library')?.status).not.toBe('done')
  expect(stages.find(s => s.key === 'publish')?.status).not.toBe('done')
})
