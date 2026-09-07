from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from quant_research.m3.campaign import CampaignLedger, CampaignSpec
from quant_research.m3.generation import ModelEndpoint, generate


def example():
    return json.loads((Path(__file__).resolve().parents[1]/'configs/m3/paper_pilot.json').read_text())['candidates'][0]


@contextmanager
def endpoint(response, protocol='ollama', status=200):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            value=response(len(requests)) if callable(response) else response
            self.send_response(status);self.end_headers();self.wfile.write(json.dumps(value).encode())
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield ModelEndpoint(f'http://127.0.0.1:{server.server_port}/chat','test-model',protocol,output_tokens=500), requests
    finally:server.shutdown();server.server_close();thread.join()


def ledger(tmp_path):
    obj=CampaignLedger(tmp_path/'campaign.sqlite')
    obj.create(CampaignSpec('test',['2015-01-01','2016-12-31'],3,2,2,1000,2,42,'transport test'))
    return obj


def test_real_http_generation_is_budgeted_and_source_cannot_be_spoofed(tmp_path):
    obj=ledger(tmp_path)
    raw={'done':True,'message':{'content':json.dumps({'candidates':[example()]})},'eval_count':100}
    with endpoint(raw) as (model,requests):
        result=generate(obj,'test',0,model,'new hypothesis',example())
    assert result['proposals'][0]['status']=='ACCEPTED'
    snap=obj.snapshot('test');proposal=json.loads(snap['proposals'][0]['payload'])
    assert proposal['source_type']=='LLM_GENERATED'
    assert proposal['source_url']=='model://test-model'
    assert requests[0]['options']['num_predict']==500 and requests[0]['stream'] is False
    assert json.loads(snap['calls'][0]['request'])['messages'][0]['role']=='system'


def test_chat_completions_protocol(tmp_path):
    raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'candidates':[example()]})}}],
         'usage':{'completion_tokens':101}}
    with endpoint(raw,'chat_completions') as (model,seen):
        generate(ledger(tmp_path),'test',0,model,'test',example())
    assert seen[0]['max_tokens']==500


def test_malformed_response_keeps_failed_call_and_budget(tmp_path):
    obj=ledger(tmp_path)
    with endpoint({'done':True,'message':{'content':'not json'},'eval_count':20}) as (model,_):
        with pytest.raises(ValueError):generate(obj,'test',0,model,'test',example())
    snap=obj.snapshot('test');assert snap['calls'][0]['state']=='FAILED'
    assert len(snap['proposals'])==0
    assert snap['calls'][0]['output_budget']==500


def test_invalid_formula_is_retained_as_invalid_proposal(tmp_path):
    item={**example(),'expression':'Ref(close,-1)'}
    obj=ledger(tmp_path)
    with endpoint({'done':True,'message':{'content':json.dumps({'candidates':[item]})}}) as (model,_):
        result=generate(obj,'test',0,model,'test',example())
    assert result['proposals'][0]['status']=='INVALID'


def test_unverified_feedback_rejected_without_call(tmp_path):
    obj=ledger(tmp_path)
    with pytest.raises(ValueError,match='earlier accepted|exactly match'):
        generate(obj,'test',1,ModelEndpoint('http://localhost/chat','none'),'test',example(),parents=[1],
                 feedback={'1':{'scope':'research_only','rank_ic':.9}})
    assert not obj.snapshot('test')['calls']


@pytest.mark.parametrize('url',['http://example.com/chat','https://user:secret@example.com/chat','https://example.com/chat?api_key=secret'])
def test_credentials_and_plaintext_remote_endpoints_rejected(url):
    with pytest.raises(ValueError):ModelEndpoint(url,'test')
