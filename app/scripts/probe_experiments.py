"""M12 read-only acceptance through the real authenticated Java API."""
import http.cookiejar
import json
import urllib.request
from probe_auth import exchange,ROOT

def run():
    accounts=json.loads((ROOT/'runtime/private-config/accounts.json').read_text())
    def login(name):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _,token=exchange(opener,'/api/auth/csrf');token=token['data']
        assert exchange(opener,'/api/auth/login',{'username':name,'password':accounts[name]},{token['headerName']:token['token']})[0]==200
        return opener
    admin=login('admin');path='/api/experiments/pawsx-zh-round2/bundle'
    status,body=exchange(admin,path);assert status==200;bundle=body['data'];manifest=bundle['manifest']
    assert len(manifest['models'])==6 and len(manifest['chartCapabilities'])==20 and len(bundle['search']['configurations'])==20
    metrics=bundle['metrics']['sets'];assert abs(metrics['official_test']['models']['bert']['macro_f1']-.7369837959240795)<1e-12
    assert abs(metrics['test_no_val_overlap']['models']['bert']['macro_f1']-.7239446804664196)<1e-12
    assert len(next(r for r in bundle['history']['runs'] if r['family']=='bert' and r['selected'])['epochs'])==2
    assert bundle['curves']['sets']['official_test']['models']['svm']['scoreType']=='decision_margin'
    _,again=exchange(admin,path);assert again['data']['manifest']['contentVersion']==manifest['contentVersion']
    roles={name:exchange(login(name),path)[0] for name in ('member1','member2','reviewer')};assert set(roles.values())=={403}
    summary={'stage':'M12','realHttp':True,'trainingTriggered':False,'contentVersion':manifest['contentVersion'],'models':6,'searchConfigurations':20,'chartCapabilities':20,
        'bertMacroF1':{key:value['models']['bert']['macro_f1'] for key,value in metrics.items()},'testSampleCounts':{key:value['n'] for key,value in metrics.items()},
        'actualHistoryPoints':{f"{run['family']}/{run['index']}":len(run['epochs']) for run in bundle['history']['runs']},'rolesRejected':roles,'unchangedRefreshRetainedVersion':True,
        'limitations':manifest['notes']}
    target=ROOT/'docs/midterm/evidence/M12-experiments.json';target.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'stage':'M12','verified':True,'models':6,'configurations':20}))

if __name__=='__main__':run()
