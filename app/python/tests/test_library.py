import unittest
from campus_detection.library import artifact_cache_key,validate_feature_space,validate_image_feature
from campus_shared.contracts import ContractError

class LibraryContractTest(unittest.TestCase):
    def test_same_image_different_preprocessor_cannot_reuse_cached_feature(self):
        a=artifact_cache_key('a'*64,{'weight':'same','processor':'first'})
        b=artifact_cache_key('a'*64,{'weight':'same','processor':'second'})
        self.assertNotEqual(a,b)
    def test_incompatible_feature_space_is_rejected(self):
        with self.assertRaises(ContractError):validate_feature_space({'featureSpaceId':'old'},{'featureSpaceId':'new'})
    def test_corrupt_cached_vector_is_rejected(self):
        for vector in ([0.0]*384,[float('nan')]*384,[1.0]):
            with self.assertRaises(ContractError):validate_image_feature({'vector':vector})

if __name__=='__main__':unittest.main()
