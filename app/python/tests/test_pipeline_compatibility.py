import unittest
from campus_shared.contracts import ContractError,validate_request

class PipelineCompatibilityTest(unittest.TestCase):
    def test_old_pipeline_missing_fails_explicitly(self):
        request={'taskId':'item','attemptId':'attempt','scene':'FORMAL','versionId':'1','inputSnapshotKey':'submission:1','inputSha256':'a'*64,'libraryGenerationId':'1','configId':'old-unavailable'}
        with self.assertRaises(ContractError) as error:validate_request(request,{'configId':'new-current'},{'generationId':'1'})
        self.assertEqual(error.exception.code,'CONFIG_UNAVAILABLE')

if __name__=='__main__':unittest.main()
