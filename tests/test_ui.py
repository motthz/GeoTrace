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

def test_archive_reopen_restores_all_search_parameters(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    app,w=make_window(tmp_path,monkeypatch)
    q=Query(lat=40.7128,lon=-74.006,location='New York',zone='America/New_York',radius=5000,mode='DEEP',keywords='fixture',media=('satellite',))
    id=w.archive.create(q);w.archive.status(id,'Earth Search',status='SUCCESS')
    monkeypatch.setattr(QInputDialog,'getItem',lambda *args,**kwargs:(f'fixture | {id}',True))
    w.reopen()
    assert w.inputs['location'].text()=='New York'
    assert w.coords()==('40.7128','-74.006')
    assert w.inputs['zone'].text()=='America/New_York'
    assert not w.auto_zone.isChecked()
    assert w.inputs['keywords'].text()=='fixture'
    assert w.radius.value()==5000 and w.mode.currentText()=='DEEP'
    assert w.source_checks['Earth Search'].isChecked()
    assert not w.source_checks['Copernicus'].isChecked()
    assert w.media_checks['satellite'].isChecked() and not w.media_checks['image'].isChecked()
    w.close()

def test_initial_actions_and_immutable_result_table(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QAbstractItemView
    app,w=make_window(tmp_path,monkeypatch)
    assert not w.cancel.isEnabled() and not w.save.isEnabled()
    assert w.table.editTriggers()==QAbstractItemView.NoEditTriggers
    w.set_search_running(True)
    assert not w.controls.isEnabled() and not w.reopen_button.isEnabled()
    w.set_search_running(False);w.close()

def test_bad_timestamp_still_renders_and_metadata_clears(tmp_path,monkeypatch):
    from geotrace.core import Record
    app,w=make_window(tmp_path,monkeypatch);id=w.archive.create(Query())
    w.archive.save(id,Record('fixture','1','https://example.com','fixture','image',{},recording='not-a-date'))
    w.render(id);assert 'not-a-date' in w.timeline.toPlainText()
    w.table.selectRow(0);assert 'fixture' in w.details.toPlainText()
    empty=w.archive.create(Query());w.render(empty)
    assert 'Select a result' in w.details.toPlainText()
    assert 'No known' in w.timeline.toPlainText();w.close()

def test_export_button_accept_and_cancel(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    app,w=make_window(tmp_path,monkeypatch);id=w.archive.create(Query());w.render(id)
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args,**kwargs:str(tmp_path/'exports'))
    w.export();assert (tmp_path/'exports'/id/'manifest.json').exists()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args,**kwargs:'')
    w.export();assert len(list((tmp_path/'exports').iterdir()))==1;w.close()

def test_map_single_click_opens_exact_record(tmp_path,monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt,QPointF
    from geotrace.core import Record
    app,w=make_window(tmp_path,monkeypatch);w.show()
    id=w.archive.create(Query());r=Record('fixture','1','https://example.com','map fixture','image',{},lat=46.24645,lon=9.42375)
    w.archive.save(id,r);w.render(id);w.tabs.setCurrentWidget(w.map);app.processEvents()
    position=w.map.mapFromScene(QPointF(r.lon,-r.lat))
    QTest.mouseClick(w.map.viewport(),Qt.LeftButton,pos=position)
    assert w.tabs.currentWidget()==w.details and r.id in w.details.toPlainText();w.close()

def test_dateline_point_stays_near_search_center():
    from geotrace.app import map_longitude
    assert abs(map_longitude(-179.99,179.99)-180.01)<1e-9

def test_search_waits_for_complete_geocoding_thread(tmp_path,monkeypatch):
    import geotrace.providers as providers
    from PySide6.QtCore import QEventLoop,QTimer
    from geotrace.core import Record
    class FixtureProvider(providers.Provider):
        async def search(self,*args):return [Record('Fixture','1','https://example.com','fixture','image',{})]
    items=[FixtureProvider(providers.Capabilities('Fixture','https://example.com',media=('image',)))]
    monkeypatch.setattr(providers,'PROVIDERS',items);monkeypatch.setattr('geotrace.app.PROVIDERS',items)
    async def locate(*args):return [{'lat':'41.9','lon':'12.5','display_name':'Roma fixture'}]
    monkeypatch.setattr('geotrace.app.geocode',locate)
    app,w=make_window(tmp_path,monkeypatch)
    w.inputs['location'].setText('Roma fixture');w.begin()
    loop=QEventLoop();timer=QTimer();timer.setInterval(20)
    timer.timeout.connect(lambda:loop.quit() if w.worker and not w.worker.isRunning() and w.start.isEnabled() else None)
    timer.start();QTimer.singleShot(5000,loop.quit);loop.exec();timer.stop()
    assert w.worker is not None and not w.worker.isRunning()
    assert w.table.rowCount()==1 and w.start.isEnabled()
    assert w.archive.load(w.current)['query']['lat']==41.9;w.close()

def test_worker_can_be_cancelled_before_thread_start(tmp_path,monkeypatch):
    from geotrace.app import Worker
    from PySide6.QtCore import QEventLoop,QTimer
    app,w=make_window(tmp_path,monkeypatch)
    worker=Worker(w.archive,Query(),[]);worker.cancel()
    loop=QEventLoop();worker.finished.connect(loop.quit);QTimer.singleShot(5000,loop.quit)
    worker.start();loop.exec();worker.wait(1000)
    assert not worker.isRunning()
    assert 'Cancelled' in w.archive.load(worker.id)['coverage']['Search coordinator']['reason'];w.close()

def test_original_browser_link_dispatch(tmp_path,monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from geotrace.core import Record
    app,w=make_window(tmp_path,monkeypatch);id=w.archive.create(Query())
    w.archive.save(id,Record('fixture','1','https://example.com/original','fixture','image',{}));w.render(id)
    urls=[];monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:urls.append(url.toString()) or True)
    w.open_record(0,0);assert urls==['https://example.com/original'];w.close()

def test_incompatible_source_media_selection_is_blocked(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch);errors=[];monkeypatch.setattr(w,'error',errors.append)
    for name,check in w.media_checks.items():check.setChecked(name=='article')
    w.begin();assert w.worker is None and errors and 'supportano' in errors[0];w.close()

def test_gallery_time_uses_investigation_zone(tmp_path,monkeypatch):
    from geotrace.core import Record
    app,w=make_window(tmp_path,monkeypatch);id=w.archive.create(Query())
    r=Record('fixture','1','https://example.com','fixture','image',{},recording='2026-10-31T00:30:00Z')
    w.archive.save(id,r);w.render(id)
    assert w.table.item(0,3).text()=='2026-10-31T01:30:00+01:00'
    assert w.archive.load(id)['records'][0]['recording']=='2026-10-31T00:30:00Z';w.close()

def test_rapid_coordinate_edits_resolve_the_final_pair(tmp_path,monkeypatch):
    import asyncio
    from PySide6.QtCore import QEventLoop,QTimer
    calls=[]
    async def geocode(text,reverse=False):
        calls.append(text);await asyncio.sleep(.1);return {'display_name':'Point '+text}
    monkeypatch.setattr('geotrace.app.geocode',geocode)
    app,w=make_window(tmp_path,monkeypatch)
    w.inputs['lat'].setText('40.7128');w.auto_coordinates()
    w.inputs['lon'].setText('-74.006');w.auto_coordinates()
    loop=QEventLoop();timer=QTimer();timer.setInterval(20)
    timer.timeout.connect(lambda:loop.quit() if w.resolved_coords==w.coords() and len(calls)==2 else None)
    timer.start();QTimer.singleShot(5000,loop.quit);loop.exec();timer.stop()
    if hasattr(w,'geo'):w.geo.wait(1000)
    assert len(calls)==2 and calls[-1]=='40.7128,-74.006'
    assert w.resolved_coords==w.coords() and w.inputs['location'].text()=='Point 40.7128,-74.006'
    assert w.inputs['zone'].text()=='America/New_York';w.close()

def test_stale_geocoding_error_does_not_interrupt_new_input(tmp_path,monkeypatch):
    app,w=make_window(tmp_path,monkeypatch);errors=[];monkeypatch.setattr(w,'error',errors.append)
    w.geo_snapshot=(w.resolved_location,w.coords(),True)
    w.inputs['lat'].setText('40.7128');w.geo_refresh_pending=True
    w.geo_error('Old request failed')
    assert not errors and w.inputs['lat'].text()=='40.7128';w.close()
