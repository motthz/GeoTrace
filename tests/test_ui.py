import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from geotrace.app import Window
from geotrace.core import Archive,Query

def test_ui_archive(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(); id=w.archive.create(Query()); w.render(id)
    assert w.table.rowCount()==0
    assert w.tabs.count()==6
    w.close()

def test_start_search_saves_and_displays_results(tmp_path,monkeypatch):
    import time
    import geotrace.providers as providers
    from geotrace.core import Record
    from PySide6.QtTest import QTest
    class FixtureProvider(providers.Provider):
        async def search(self,*args):
            return [Record('UI fixture','one','https://example.com/media','UI workflow fixture','image',{},lat=46.24645,lon=9.42375)]
    monkeypatch.setattr(providers,'PROVIDERS',[FixtureProvider(providers.Capabilities('UI fixture','https://example.com',media=('image',)))])
    monkeypatch.setattr('geotrace.app.PROVIDERS',providers.PROVIDERS)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(); w.begin()
    deadline=time.monotonic()+5
    while w.worker.isRunning() and time.monotonic()<deadline: QTest.qWait(20)
    app.processEvents()
    assert w.table.rowCount()==1
    assert w.start.isEnabled()
    assert w.archive.load(w.current)['records'][0]['title']=='UI workflow fixture'
    assert 'SUCCESS' in w.coverage.toPlainText()
    assert 'youtube.com/results' in w.links.toHtml()
    assert w.map.transform().m11()>100
    id=w.current; w.render(id); assert w.table.rowCount()==1
    w.close()

def test_changed_location_resolves_before_search(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(); called=[]
    monkeypatch.setattr(w,'locate_place',lambda:called.append(True))
    w.inputs['location'].setText('Roma'); w.begin()
    assert called and w.pending_search
    assert w.worker is None
    w.close()
