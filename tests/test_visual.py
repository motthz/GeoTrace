"""Image fixtures are generated only in tests; never inserted in real searches."""
import dataclasses,json,time,os,asyncio
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QBuffer,QIODevice,Qt,QEventLoop,QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from geotrace.images import ImageCache,ImageBroker,image_url_allowed,image_expiry,decode_image,MAX_BYTES
from geotrace.basemap import project,circle,MERCATOR_LIMIT
from geotrace.core import distance,Query,Record
from geotrace.app import Window

def png(width=256,height=256):
    image=QImage(width,height,QImage.Format_RGB32);image.fill(Qt.red)
    buffer=QBuffer();buffer.open(QIODevice.WriteOnly);assert image.save(buffer,'PNG');return bytes(buffer.data())

@pytest.mark.parametrize('url',['http://upload.wikimedia.org/a','https://localhost/a','https://wikimedia.org.evil.test/a','https://user:password@upload.wikimedia.org/a','s3://bucket/image.jpg','https://upload.wikimedia.org:123/a',{'bad':'url'}])
def test_preview_urls_are_constrained(url):assert not image_url_allowed(url)

def test_public_hosts_and_tile_role_are_separate():
    assert image_url_allowed('https://thumb.wikimedia.org/a.png')
    assert image_url_allowed('https://tile.openstreetmap.org/1/1/1.png','tile')
    assert not image_url_allowed('https://tile.openstreetmap.org/1/1/1.png','preview')

def test_expiry_honors_cache_headers():
    assert image_expiry({},'tile',0)==7*86400
    assert image_expiry({'cache-control':'max-age=600','age':'200'},'tile',0)==400
    assert image_expiry({'cache-control':'no-store'},'tile',0) is None
    assert image_expiry({'cache-control':'no-cache'},'preview',0) is None

def test_image_cache_integrity_expiration_and_quota(tmp_path):
    cache=ImageCache(tmp_path,max_bytes=10)
    cache.write('one',b'12345',time.time()+100);assert cache.read('one')==b'12345'
    cache.paths('one')[0].write_bytes(b'changed');assert cache.read('one') is None
    cache.write('two',b'1234567890',time.time()+100)
    assert sum(p.stat().st_size for p in tmp_path.glob('*.bin'))<=10
    assert cache.read('two')==b'1234567890'
    meta=cache.paths('two')[1];info=json.loads(meta.read_text());info['expires']=0;meta.write_text(json.dumps(info));assert cache.read('two') is None

def test_decode_dimensions_format_and_preview_scale():
    assert decode_image(png(),'tile').width()==256
    preview=decode_image(png(800,400),'preview');assert (preview.width(),preview.height())==(240,120)
    for body,kind in [(png(5000,2),'preview'),(png(240,240),'tile'),(b'<svg/>','preview'),(b'x'*(MAX_BYTES+1),'preview')]:
        with pytest.raises(ValueError):decode_image(body,kind)

def test_web_mercator_and_dateline():
    p=project(0,0);assert (p.x(),p.y())==(128,128)
    assert abs(project(0,-179.99,179.99).x()-project(0,179.99,179.99).x())<.02
    with pytest.raises(ValueError):project(90,0)

def test_geodesic_search_circle_uses_radius():
    points=circle(46.24645,9.42375,1000)
    assert len(points)==73
    for lat,lon in points:assert abs(distance(46.24645,9.42375,lat,lon)-1000)<.001

def test_hidden_map_does_not_fetch_tiles_and_poles_clear_old_data(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=Window()
    w.street.set_data(dataclasses.asdict(Query()),[]);w.street.update_tiles()
    assert not w.images.jobs
    w.street.set_data(dataclasses.asdict(Query(lat=89)),[])
    assert not w.street.valid and not w.street.needed and not w.street.tiles
    w.close()

def test_first_visible_map_is_centered_and_failed_tiles_reported(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=Window()
    monkeypatch.setattr(w.images,'request',lambda *args:None)
    monkeypatch.setattr(w.images,'result',lambda url,kind='preview':(QImage(),'Fixture network unavailable'))
    w.show();q=Query();w.street.set_data(dataclasses.asdict(q),[]);w.tabs.setCurrentWidget(w.street)
    loop=QEventLoop();QTimer.singleShot(250,loop.quit);loop.exec()
    center=w.street.view.mapToScene(w.street.view.viewport().rect().center());expected=project(q.lat,q.lon,q.lon)
    assert (center-expected).manhattanLength()*2**w.street.view.zoom<3
    assert w.street.needed and 'non disponibili' in w.street.status.text()
    w.close()

def test_preview_caching_toggle_and_missing_metadata(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=Window()
    url='https://thumb.wikimedia.org/fixture.png';w.images.cache.write(url,png(),time.time()+100)
    id=w.archive.create(Query());r=Record('fixture','one','https://example.com/fixture','Image fixture','image',{},thumbnail=url)
    w.archive.save(id,r);w.show();w.render(id);w.load_visible_previews()
    assert w.preview_states[r.id]=='loaded' and not w.table.item(0,0).icon().isNull()
    assert w.archive.load(id)['records'][0]['recording'] is None
    w.previews_enabled.setChecked(False);assert w.table.item(0,0).icon().isNull()
    w.previews_enabled.setChecked(True);w.load_visible_previews();assert not w.table.item(0,0).icon().isNull()
    w.close()

def test_credit_retains_author_license_and_source():
    from geotrace.images import preview_credit
    r={'provider':'Commons','url':'https://commons.wikimedia.org/wiki/File:test','license':'CC BY-SA','raw':{'imageinfo':[{'extmetadata':{'Artist':{'value':'<a href="https://example.com">Test Author</a>'}}}]}}
    text=preview_credit(r);assert 'Test Author' in text and 'CC BY-SA' in text and '<a' not in text

def test_nasa_uses_published_browse_link_without_guessing():
    from geotrace.providers import Nasa,Capabilities
    async def fixture(*args,**kwargs):return {'feed':{'entry':[{'id':'fixture','links':[{'rel':'https://esipfed.org/browse#','href':'https://data.earthdata.nasa.gov/fixture.jpg'}]}]}}
    records=asyncio.run(Nasa(Capabilities('NASA','https://example.com')).search(None,Query(),fixture))
    assert records[0].thumbnail=='https://data.earthdata.nasa.gov/fixture.jpg'
    assert records[0].download_allowed is False

def test_filter_never_displays_credit_from_a_hidden_record(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=Window()
    id=w.archive.create(Query())
    for number in ('first','second'):w.archive.save(id,Record('fixture',number,'https://example.com/'+number,number+' fixture','image',{}))
    w.render(id);w.table.selectRow(0);w.filter.setText('second fixture')
    assert w.table.currentRow()==-1 and 'Seleziona' in w.gallery_credit.text()
    record=w.records[0];w.select_record(record['id'])
    assert not w.filter.text() and w.table.currentRow()==0
    w.close()
