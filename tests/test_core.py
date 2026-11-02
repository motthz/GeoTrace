import asyncio
import dataclasses
import json
import httpx
import pytest
from geotrace.core import Query,Record,Archive,utc,canonical,distance,duplicate_groups,sha256
from geotrace.providers import request,Commons,Capabilities,search
from geotrace.media import download
from geotrace.reports import export

def test_time():
    q=Query(); assert q.start_utc=='2026-10-31T00:00:00+00:00'
    assert utc('2026-07-01T01:00:00','Europe/Rome')=='2026-06-30T23:00:00+00:00'
    with pytest.raises(ValueError): utc('2026-10-25T02:30:00','Europe/Rome')
    with pytest.raises(ValueError): utc('2026-03-29T02:30:00','Europe/Rome')
    with pytest.raises(ValueError): Query(start='2027-01-01')

def test_geo():
    assert len(Query(lon=179.99,radius=100000).boxes())==2
    assert Query(lat=90).boxes()[0][0]==-180
    assert distance(0,0,0,0)==0
    with pytest.raises(ValueError): Query(lat=91)

def test_url():
    assert canonical('https://EXAMPLE.com/a#x')=='https://example.com/a'
    for url in ('file:///a','javascript:alert(1)','https://user:pass@example.com'):
        with pytest.raises(ValueError): canonical(url)

def test_archive_reports(tmp_path):
    a=Archive(tmp_path/'test.sqlite'); id=a.create(Query()); r=Record('test','1','https://example.com','<unsafe>','image',{'original':1})
    a.save(id,r); a.save(id,r); a.status(id,'test',status='SUCCESS')
    data=a.load(id); assert len(data['records'])==1; assert data['records'][0]['recording'] is None
    export(data,tmp_path/'reports')
    assert '&lt;unsafe&gt;' in (tmp_path/'reports/report.html').read_text(encoding='utf-8')
    assert (tmp_path/'reports/report.pdf').read_bytes().startswith(b'%PDF')
    assert json.loads((tmp_path/'reports/investigation.json').read_text())['records'][0]['raw']=={'original':1}

def test_duplicates_and_hash(tmp_path):
    p=tmp_path/'a'; p.write_bytes(b'abc'); assert sha256(p)=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    assert duplicate_groups([{'id':'a','url':'https://example.com#1'},{'id':'b','url':'https://example.com#2'}])==[['a','b']]
    r=Record('test','1','https://example.com','title','image',{})
    with pytest.raises(PermissionError): download(r,tmp_path)

def test_provider_error_not_empty():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(403))) as c:
            with pytest.raises(httpx.HTTPStatusError): await request(c,'GET','https://example.com')
    asyncio.run(run())

def test_rate_limit():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(429,headers={'Retry-After':'120'}))) as c:
            with pytest.raises(httpx.HTTPStatusError): await request(c,'GET','https://example.com')
    asyncio.run(run())

def test_commons_upload_not_recording():
    async def mocked(*args,**kwargs):
        return {'query':{'pages':{'1':{'pageid':1,'title':'File:test','imageinfo':[{'descriptionurl':'https://commons.wikimedia.org/wiki/File:test','timestamp':'2026-10-31T01:00:00Z'}]}}}}
    rows=asyncio.run(Commons(Capabilities('test','https://example.com')).search(None,Query(),mocked))
    assert rows[0].upload; assert rows[0].recording is None; assert rows[0].lat is None; assert rows[0].temporal_confidence=='UNKNOWN'

def test_orchestrator_failure_and_resume(tmp_path,monkeypatch):
    import geotrace.providers as providers
    class Good(providers.Provider):
        async def search(self,*args): return [Record('good','one','https://example.com/item','real fixture','image',{})]
    class Bad(providers.Provider):
        async def search(self,*args): raise RuntimeError('broken API')
    monkeypatch.setattr(providers,'PROVIDERS',[Good(Capabilities('good','https://example.com',media=('image',))),Bad(Capabilities('bad','https://example.com'))])
    a=Archive(tmp_path/'db'); q=Query(); id=asyncio.run(search(a,q))
    assert a.load(id)['coverage']['bad']['status']=='ERROR'
    asyncio.run(search(a,q,investigation=id))
    assert len(a.load(id)['records'])==1

def test_cancellation_checkpoint(tmp_path,monkeypatch):
    import geotrace.providers as providers
    class Slow(providers.Provider):
        async def search(self,*args): await asyncio.sleep(60)
    monkeypatch.setattr(providers,'PROVIDERS',[Slow(Capabilities('slow','https://example.com'))])
    a=Archive(tmp_path/'db'); q=Query(); id=a.create(q)
    async def run():
        started=asyncio.Event()
        task=asyncio.create_task(search(a,q,lambda *args:started.set(),investigation=id))
        await started.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(run())
    assert a.load(id)['coverage']['slow']['status']=='ERROR'
