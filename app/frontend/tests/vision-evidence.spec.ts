import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import ImageEvidence from '../src/components/ImageEvidence.vue'
import OcrEvidence from '../src/components/OcrEvidence.vue'
import type { ImageEvidenceItem } from '../src/api/review'

test('renders both geometric regions and retains legacy image evidence', () => {
  const base: ImageEvidenceItem = { evidenceId: 'image', evidenceType: 'IMAGE_SIMILARITY', sourceWorkId: '1', sourceRevisionId: '2', sourceTitle: '校园图片', acceptedCandidate: true, queryFileId: '3', sourceFileId: '4', similarity: .92, threshold: .9 }
  const geometry = { status: 'CORRESPONDENCE_SUPPORTED', scope: 'LOCAL_REGION', acceptedCorrespondence: true, inliers: 32, matches: 40, querySpatialCoverage: .8, sourceSpatialCoverage: .2, querySize: { width: 400, height: 300 }, sourceSize: { width: 800, height: 600 }, queryRegion: [[0,0],[300,0],[300,200]], sourceRegion: [[50,20],[250,20],[250,200]] }
  const wrapper = mount(ImageEvidence, { props: { evidence: [{ ...base, geometry }, { ...base, evidenceId: 'legacy' }], queryFileId: '3', imageNumber: 1 }, global: { stubs: { 'el-tag': { template: '<span><slot/></span>' }, 'el-image': true, 'el-empty': true } } })
  expect(wrapper.text()).toContain('局部对应'); expect(wrapper.text()).toContain('80.0%'); expect(wrapper.text()).toContain('相似图片')
  expect(wrapper.findAll('svg')).toHaveLength(2); expect(wrapper.find('svg').attributes('viewBox')).toBe('0 0 400 300'); expect(wrapper.findAll('polygon')[1]!.attributes('points')).toBe('50,20 250,20 250,200')
  expect(wrapper.find('el-image-stub').attributes('preview-src-list')).toBe('/api/files/3')
  wrapper.unmount()
  const ocr = mount(OcrEvidence, { props: { fileId: '3', result: { processingCoverageStatus: 'PARTIAL', processingStrategy: ['mobile960','mobile1600','tile-1','tile-2'], recognitionLines: [], conflictingOcrAlternatives: [{ retained: '校园', alternative: '校图' }] } }, global: { stubs: { 'el-tag': { template: '<span><slot/></span>' }, 'el-table': true, 'el-table-column': true, 'el-alert': true } } })
  expect(ocr.text()).toContain('标准识别 → 高分辨率 → 分块2次'); expect(ocr.text()).toContain('部分区域已处理'); expect(ocr.text()).toContain('识别差异 · 1处'); ocr.unmount()
})
