"""Regression cases discovered during the user-flow audit. Fixtures are synthetic."""
import asyncio
import csv
import dataclasses
import json
import sqlite3
from datetime import datetime,timezone,timedelta
from email.utils import format_datetime
import httpx
import pytest
from geotrace.core import Archive,Query,Record,sha256
from geotrace.providers import Stac,Nasa,Commons,Capabilities,search,request
from geotrace.reports import export

@pytest.mark.parametrize('params',[
    {'end':'2026-10-31T01:00:00'},
    {'media':()}, {'media':('typo',)}, {'media':'image'},
    {'start':'2026-10-31T01:00:00Z','zone':'Bad/Zone'},
    {'lat':float('nan')},{'lon':float('inf')},
])
def test_query_rejects_inconsistent_input(params):
    with pytest.raises((ValueError,KeyError)):Query(**params)

def test_newer_database_not_downgraded(tmp_path):
    path=tmp_path/'db'
    with sqlite3.connect(path) as c:c.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError):Archive(path)
    with sqlite3.connect(path) as c:assert c.execute('PRAGMA user_version').fetchone()[0]==99

def test_database_connections_close(tmp_path):
    archive=Archive(tmp_path/'db')
    with archive.connect() as connection: connection.execute('SELECT 1')
    with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')

@pytest.mark.parametrize('provider',[Stac(Capabilities('STAC','https://example.com')),Nasa(Capabilities('NASA','https://example.com'))])
def test_malformed_api_payload_is_failure(provider):
    async def malformed(*args,**kwargs):return {'error':'provider temporarily broken'}
    with pytest.raises(RuntimeError):asyncio.run(provider.search(None,Query(),malformed))

def test_resume_cannot_mix_queries(tmp_path):
    archive=Archive(tmp_path/'db');id=archive.create(Query())
    with pytest.raises(ValueError):asyncio.run(search(archive,Query(radius=2000),investigation=id))

def test_unknown_source_rejected_before_investigation(tmp_path):
    archive=Archive(tmp_path/'db')
    with pytest.raises(ValueError):asyncio.run(search(archive,Query(),selected=['Unknown']))
    assert not archive.list()

def test_http_date_retry_after_is_respected():
    async def run():
        retry=format_datetime(datetime.now(timezone.utc)+timedelta(minutes=5),usegmt=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(429,headers={'Retry-After':retry}))) as client:
            with pytest.raises(httpx.HTTPStatusError):await request(client,'GET','https://example.com')
    asyncio.run(run())

def test_retry_recovers_transient_server_error(monkeypatch):
    import geotrace.providers as providers
    calls=[];delays=[]
    def respond(req):
        calls.append(1)
        return httpx.Response(503) if len(calls)==1 else httpx.Response(200,json={'ok':True})
    async def sleep(delay):delays.append(delay)
    monkeypatch.setattr(providers.asyncio,'sleep',sleep)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:assert await request(client,'GET','https://example.com')=={'ok':True}
    asyncio.run(run());assert delays==[1];assert len(calls)==2

def test_commons_partial_coordinate_and_video_mime():
    async def fixture(*args,**kwargs):return {'query':{'pages':{'1':{'pageid':1,'title':'File:fixture','coordinates':[{'lat':1}], 'imageinfo':[{'descriptionurl':'https://example.com','mime':'video/mp4'}]}}}}
    records=asyncio.run(Commons(Capabilities('Commons','https://example.com')).search(None,Query(),fixture))
    assert records[0].lat is None and records[0].lon is None
    assert records[0].media=='video'

def test_report_manifest_and_csv_formulas(tmp_path):
    a=Archive(tmp_path/'db');id=a.create(Query());r=Record('fixture','one','https://example.com','=1+1','image',{'unaltered':'<value>'})
    a.save(id,r);data=a.load(id);export(data,tmp_path/'report')
    manifest=json.loads((tmp_path/'report/manifest.json').read_text())
    assert len(manifest['files'])==4
    for name,digest in manifest['files'].items():assert sha256(tmp_path/'report'/name)==digest
    with (tmp_path/'report/results.csv').open(encoding='utf-8-sig',newline='') as f:assert next(csv.DictReader(f))['title']=="'=1+1"
    assert json.loads((tmp_path/'report/investigation.json').read_text())['records'][0]['title']=='=1+1'

def test_export_failure_does_not_replace_existing_report(tmp_path,monkeypatch):
    import geotrace.reports as reports
    a=Archive(tmp_path/'db');id=a.create(Query());folder=tmp_path/'report';folder.mkdir();existing=folder/'report.html';existing.write_text('original')
    def broken(data,staging):
        (staging/'report.html').write_text('partial');raise OSError('Disk failure fixture')
    monkeypatch.setattr(reports,'_write',broken)
    with pytest.raises(OSError):reports.export(a.load(id),folder)
    assert existing.read_text()=='original'

def test_manifest_is_published_after_every_referenced_file(tmp_path,monkeypatch):
    import geotrace.reports as reports
    from pathlib import Path
    a=Archive(tmp_path/'db');id=a.create(Query());published=[];replace=reports.os.replace
    def track(source,destination):
        if Path(source).name=='manifest.json':
            metadata=json.loads(Path(source).read_text())
            assert all((Path(destination).parent/name).exists() for name in metadata['files'])
        published.append(Path(source).name);replace(source,destination)
    monkeypatch.setattr(reports.os,'replace',track)
    reports.export(a.load(id),tmp_path/'exports');assert published[-1]=='manifest.json'

@pytest.mark.parametrize('stamp',[None,'invalid','2024-01-01T10:00:00'])
def test_unconfirmed_time_does_not_get_metadata_confidence(stamp):
    from geotrace.providers import time_confidence
    assert time_confidence(stamp)=='UNKNOWN'

def test_real_timestamp_confidence():
    from geotrace.providers import time_confidence
    assert time_confidence('2024-01-01T10:00:00Z')=='METADATA_SUPPORTED'

@pytest.mark.parametrize('value',['=1+1','+SUM(1)','-1+1','@cmd','\tformula'])
def test_spreadsheet_special_text_escaped(value):
    from geotrace.reports import csv_value
    assert csv_value(value).startswith("'")

def test_download_rejects_unsafe_local_identifier(tmp_path):
    from geotrace.media import download
    r=Record('fixture','1','https://example.com','fixture','image',{},id='../escape',download_allowed=True,download_url='https://example.com/file')
    with pytest.raises(ValueError):download(r,tmp_path)
