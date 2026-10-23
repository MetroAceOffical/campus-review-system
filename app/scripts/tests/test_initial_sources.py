import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from initial_sources import prepare_sources

class InitialSourceTest(unittest.TestCase):
    def test_official_sources_are_grouped_without_synthetic_or_publication(self):
        result=prepare_sources()
        self.assertEqual(result['textCount'],194)
        self.assertEqual(result['imageCount'],59)
        self.assertEqual(len(result['works']),196)
        self.assertEqual(len({work['url'] for work in result['works']}),196)
        self.assertTrue(all(len(work['images'])<=6 for work in result['works']))
        self.assertTrue(all(image['sourceMetadata']['source_kind']=='official_public_article_image'
                            for work in result['works'] for image in work['images']))
        self.assertTrue(all('publicationState' not in work for work in result['works']))
