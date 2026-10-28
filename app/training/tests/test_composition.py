import hashlib,json,sys,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/python'))
from campus_workbench import composition


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'runtime');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.boundary=self.root/'runtime/workbench/datasets';self.boundary.mkdir(parents=True)
        self.patch=patch.object(composition,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)

    def source(self,rows,name):
        dataset,version=str(uuid.uuid4()),str(uuid.uuid4());folder=self.boundary/dataset/version;folder.mkdir(parents=True)
        path=folder/'corpus.jsonl';path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
        return {'datasetId':dataset,'versionId':version,'name':name,'sha256':composition.sha(path)}

    def run_compose(self,sources,kind='NEWS'):
        folder=self.boundary/str(uuid.uuid4());folder.mkdir();input=folder/'sources.json';composition.write(input,{'schemaVersion':1,'kind':kind,'sources':sources});events=[]
        manifest=composition.compose(input,folder/'output',kind,events.append)
        self.assertEqual(events[-1]['stage'],'COMPLETED');self.assertTrue((folder/'output/manifest.json').is_file())
        for name,sha in manifest['artifacts'].items():self.assertEqual(composition.sha(folder/'output'/name),sha)
        return folder/'output',manifest

    def test_news_namespaces_ids_merges_duplicates_and_keeps_all_origins(self):
        a=self.source([{'id':'1','text':'同一新闻😀','split':'train','_provenance':[{'id':'原A','url':'https://example.com/a'}]},{'id':'2','text':'第二则'}],'A')
        b=self.source([{'id':'1','text':'同一新闻😀','split':'train','_provenance':[{'id':'原B','url':'https://example.com/b'}]},{'id':'2','text':'第三则'}],'B')
        output,result=self.run_compose([a,b]);self.assertEqual((result['inputRows'],result['outputRows'],result['duplicateRows']),(4,3,1))
        records=[json.loads(line) for line in (output/'corpus.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len({r['id'] for r in records}),3);same=next(r for r in records if r['text']=='同一新闻😀')
        self.assertEqual({r['id'] for r in same['_provenance']},{'原A','原B'});self.assertEqual(same['split'],'train')
        lineage=[json.loads(line) for line in (output/'lineage.jsonl').read_text(encoding='utf-8').splitlines()];self.assertEqual(len(lineage),4)
        self.assertEqual(sum(r['action']=='DUPLICATE' for r in lineage),1)

    def test_partition_and_pair_label_conflicts_are_quarantined_without_relabelling(self):
        a=self.source([{'id':'1','text':'跨分区新闻','split':'train'}],'A');b=self.source([{'id':'1','text':'跨分区新闻','split':'test'}],'B')
        _,result=self.run_compose([a,b]);self.assertEqual((result['outputRows'],result['quarantineRows']),(0,2))
        a=self.source([{'id':'1','sentence1':'甲','sentence2':'乙','label':1}],'A');b=self.source([{'id':'1','sentence1':'乙','sentence2':'甲','label':0}],'B')
        _,result=self.run_compose([a,b],'PAIRS');self.assertEqual((result['outputRows'],result['quarantineRows']),(0,2))

    def test_source_change_is_rejected_before_creating_output(self):
        a=self.source([{'text':'原稿'}],'A');b=self.source([{'text':'另稿'}],'B')
        (self.boundary/a['datasetId']/a['versionId']/'corpus.jsonl').write_text('{}\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'校验'):self.run_compose([a,b])
        self.assertFalse(any(self.boundary.glob('*/output/manifest.json')))


if __name__=='__main__':unittest.main()
