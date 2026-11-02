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

def make_window(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    return app,Window()

def test_coordinates_fill_label_and_zone_without_moving_point(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch)
    monkeypatch.setattr(w,'locate_place',lambda:None)
    w.inputs['lat'].setText('40,7128'); w.inputs['lon'].setText('-74.006'); w.auto_coordinates()
    assert w.coords()==('40.7128','-74.006')
    assert w.inputs['zone'].text()=='America/New_York'
    assert w.inputs['location'].text()=='40.7128, -74.006'
    w.geo_snapshot=(w.resolved_location,w.coords(),True)
    w.located({'display_name':'New York'})
    assert w.inputs['location'].text()=='New York'
    assert w.coords()==('40.7128','-74.006')
    assert w.resolved_coords==w.coords()
    w.close()

def test_stale_lookup_cannot_overwrite_new_coordinates(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch)
    w.geo_snapshot=(w.resolved_location,w.coords(),False)
    w.inputs['lat'].setText('41.9')
    w.located([{'lat':'48.8','lon':'2.3','display_name':'Paris'}])
    assert w.inputs['lat'].text()=='41.9'
    assert w.resolved_location=='Samolaco railway station, Italy'
    w.close()

def test_dates_normalize_and_preserve_duration(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch)
    w.inputs['start'].setText('05/11/2026 23:30'); assert w.normalize_dates('start')
    assert w.inputs['start'].text()=='2026-11-05T23:30:00'
    assert w.inputs['end'].text()=='2026-11-06T00:30:00'
    w.inputs['end'].setText('05/11/2026 22:30')
    assert not w.normalize_dates('end')
    w.close()

def test_manual_timezone_is_preserved(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch)
    w.auto_zone.setChecked(False); w.inputs['zone'].setText('UTC'); w.fill_zone()
    assert w.inputs['zone'].text()=='UTC'
    assert not w.inputs['zone'].isReadOnly()
    w.close()

def test_invalid_coordinates_do_not_leave_search_disabled(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch)
    w.inputs['lat'].setText('999'); w.begin()
    assert w.start.isEnabled(); assert w.worker is None
    w.close()
