"""Synthetic permissions and text only. Not a real source authorization."""
from ssr_collector_peak.primitives import utc_now


def source():
    return {'source_id':'synthetic-source','url':'https://example.test/peak-fixture','source_type':'official',
        'title':'Synthetic fixture, not real PEAK knowledge','language':'en','declared_version':'synthetic-v1',
        'selector':{'tag':'main'},'interval_seconds':2,'policy':{'allow_fetch':True,'reviewed_at':utc_now(),
            'terms_url':'https://example.test/terms','notes':'Synthetic transport only; no website permission.',
            'uses':{p:{'status':'allowed','basis':'Synthetic test only.'} for p in ['local_cache','search_index','ai_input','ai_train']}}}
