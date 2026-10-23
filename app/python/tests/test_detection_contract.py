import hashlib
import unittest
from campus_shared.contracts import ContractError, validate_request, validate_result
from campus_detection.text import detect_text


def request(text='测试正文', scene='FORMAL'):
    return {'taskId':'1','attemptId':'1','scene':scene,'versionId':'1',
            'inputSnapshotKey':'submission:1','inputSha256':hashlib.sha256(b'immutable-snapshot').hexdigest(),
            'libraryGenerationId':'1','text':text,'excludeManuscriptId':'17','configId':'text-test'}


class DetectionContractTest(unittest.TestCase):
    def test_mismatched_identity_or_configuration_is_rejected(self):
        original=request()
        for key in ('attemptId','inputSha256','inputSnapshotKey','libraryGenerationId','configId'):
            changed=dict(original,**{key:'different'})
            with self.assertRaises(ContractError): validate_result(changed,original)
        with self.assertRaises(ContractError): validate_request(dict(original,configId='unknown'),{'configId':'text-test'}, {'generationId':'1'})

    def test_empty_library_is_limited_without_claiming_no_reuse(self):
        result=detect_text(request(),{'generationId':'1','documents':[]},{'textConfig':{'configId':'text-test'}})
        self.assertEqual(result['status'],'COMPLETED')
        self.assertIn('EMPTY_LIBRARY',result['qualityFlags'])
        self.assertFalse(result['noReuseClaim'])
        self.assertEqual(result['evidence'],[])

    def test_core_does_not_require_a_submission_database_row(self):
        result=detect_text(request(scene='PRECHECK'),{'generationId':'1','documents':[]},{'textConfig':{'configId':'text-test'}})
        self.assertEqual(result['scene'],'PRECHECK')
        self.assertFalse(result['noReuseClaim'])


if __name__=='__main__': unittest.main()
