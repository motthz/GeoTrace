"""Drive a real Windows GeoTrace window via UI Automation, using a private archive.

Run from repository root: python tools/audit_desktop.py [--exe PATH]
Requires optional pywinauto. Uses real public providers; never inserts fixtures.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geotrace.core import Archive,sha256

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path);parser.add_argument('--output',type=Path,default=ROOT/'private/audit/desktop')
    args=parser.parse_args();folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=True)
    from pywinauto import Application,Desktop,keyboard
    from pywinauto.controls.hwndwrapper import HwndWrapper
    env=dict(os.environ);env.pop('QT_QPA_PLATFORM',None);env['LOCALAPPDATA']=str(folder/'profile')
    checks=[];process=None;win=None
    def record(name,details=''):
        checks.append({'check':name,'status':'PASS','details':details});print('PASS:',name,details,flush=True)
    def wait_for(predicate,timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.2)
        raise TimeoutError('UI condition did not complete')
    def screen(name,window=None):
        target=window or win;target.capture_as_image().save(str(folder/(name+'.png')))
    def control(name,kind):
        matches=[c for c in win.descendants(control_type=kind) if c.element_info.name==name]
        if len(matches)!=1:raise RuntimeError('Control lookup failed: '+name+' ('+kind+')')
        return matches[0]
    def button(name):return control(name,'Button')
    def edit(name):
        matches=[c for c in win.descendants(control_type='Edit') if c.element_info.name==name]
        if len(matches)!=1:raise RuntimeError('Edit lookup failed: '+name+'; available='+str([(c.element_info.name) for c in win.descendants(control_type='Edit')]))
        return matches[0]
    def text(name,value):
        control=edit(name);control.set_edit_text(value);control.type_keys('{TAB}');time.sleep(.15)
    def dialog(title):
        found=[]
        def lookup():
            matches=[c for c in win.descendants(control_type='Window') if c.element_info.name==title]
            if not matches:matches=[c for c in Desktop(backend='uia').windows(process=process.pid) if c.element_info.name==title]
            found[:]=matches
            return bool(matches)
        wait_for(lookup,25);return found[0]
    def click_dialog_button(window,names):
        for name in names:
            candidates=[c for c in window.descendants(control_type='Button') if c.element_info.name==name]
            if candidates:candidates[0].click_input();return
        raise RuntimeError('No expected button: '+str([(b.window_text()) for b in window.descendants(control_type='Button')]))
    archive=Archive(folder/'profile/GeoTrace/archive.sqlite')
    def open_archive(id):
        button('Open archived investigation').click_input();picker=dialog('Investigations');screen('07-archive-dialog',picker)
        created=dict(archive.list())[id]
        picker.descendants(control_type='ComboBox')[0].select(created+' | '+id)
        click_dialog_button(picker,['OK']);wait_for(lambda:button('Start search').is_enabled())
    def launch():
        nonlocal process,win
        command=[str(args.exe.resolve())] if args.exe else [sys.executable,'-m','geotrace.app']
        process=subprocess.Popen(command,cwd=ROOT,env=env)
        application=Application(backend='uia').connect(process=process.pid,timeout=30)
        win=application.window(title_re='GeoTrace.*');win.wait('visible',timeout=30);win.set_focus()
    try:
        launch();screen('00-startup')
        assert not button('Cancel').is_enabled() and not button('Export HTML / PDF / CSV / JSON').is_enabled()
        record('Startup and initial action availability')
        HwndWrapper(win.wrapper_object().handle).move_window(x=20,y=20,width=1000,height=740);screen('01-small-window')
        assert button('Start search').is_visible() and button('Open archived investigation').is_visible()
        record('Smaller-window controls remain accessible','1000 x 740; scrollable parameters')
        HwndWrapper(win.wrapper_object().handle).move_window(x=10,y=10,width=1450,height=900)
        time.sleep(.8)
        text('start','2024-06-01T00:00:00');text('end','2024-06-30T23:59:59')
        spinner=control('Radius (m)','Spinner')
        spinner.set_focus();keyboard.send_keys('^a10000{TAB}')
        button('Start search').click_input();screen('02-search-running')
        wait_for(lambda:button('Start search').is_enabled(),150)
        rows=[(id,archive.load(id)) for id,_ in archive.list()]
        id,data=rows[0];main_id=id
        assert data['records'],'Real providers returned no media; inspect coverage rather than fabricating a screenshot'
        record('Real native search persists public provider records',str(len(data['records']))+' records; '+json.dumps({k:v['status'] for k,v in data['coverage'].items()}))
        table=win.descendants(control_type='Table')[0];table.click_input(coords=(100,50));time.sleep(.2)
        for index,name in enumerate(['Media gallery','Map (offline coordinates)','Timeline','Source coverage','Original metadata','Public search links']):
            control(name,'TabItem').select();time.sleep(.35)
            screen('03-tab-'+str(index)+'-'+name.split()[0].lower())
            record('Native screen: '+name)
        control('Media gallery','TabItem').select()
        # The unlabeled edit outside the form is the gallery filter.
        gallery_filter=edit('')
        gallery_filter.set_edit_text('NO_MATCH_AUDIT_7FC0');screen('04-no-filter-matches');gallery_filter.set_edit_text('')
        record('Gallery filter accepts and clears input')
        # A deliberately invalid coordinate must not start a new investigation.
        before=len(archive.list());text('lat','999');button('Start search').click_input();screen('05-invalid-coordinate')
        assert len(archive.list())==before and button('Start search').is_enabled();record('Invalid coordinate blocked without disabling search')
        open_archive(main_id);assert abs(float(edit('lat').get_value())-data['query']['lat'])<1e-8
        assert edit('zone').get_value()==data['query']['zone'];record('Archived search restores fields and results')
        button('Export HTML / PDF / CSV / JSON').click_input();chooser=dialog('Export destination');screen('08-export-dialog',chooser)
        click_dialog_button(chooser,['Annulla','Cancel']);record('Cancel export dialog')
        destination=folder/'exports';destination.mkdir(exist_ok=True)
        button('Export HTML / PDF / CSV / JSON').click_input();chooser=dialog('Export destination')
        chooser.set_focus();keyboard.send_keys('%d');keyboard.send_keys(str(destination),with_spaces=True);keyboard.send_keys('{ENTER}');time.sleep(.6)
        click_dialog_button(chooser,['Seleziona cartella','Selezione cartella','Select Folder','Choose','Scegli cartella'])
        wait_for(lambda:(destination/main_id/'manifest.json').exists(),60)
        report=destination/main_id;manifest=json.loads((report/'manifest.json').read_text())
        for name,digest in manifest['files'].items():assert sha256(report/name)==digest
        assert json.loads((report/'investigation.json').read_text(encoding='utf-8'))['records']==data['records']
        screen('09-export-complete');record('Export via native folder dialog','HTML/PDF/CSV/JSON + SHA-256 manifest verified')
        # Start and immediately cancel a new real query; previous investigation stays intact.
        button('Start search').click_input()
        if button('Cancel').is_enabled():button('Cancel').click_input()
        wait_for(lambda:button('Start search').is_enabled(),45);screen('10-search-cancelled')
        assert len(archive.load(main_id)['records'])==len(data['records']);record('Cancellation keeps previous evidence archive')
        win.close();process.wait(timeout=10);assert process.returncode==0;record('Clean application close')
        launch();open_archive(main_id);screen('11-restart-reopen')
        assert edit('start').get_value()==data['query']['start'];record('Process restart and archive reopen')
        win.close();process.wait(timeout=10);assert process.returncode==0
        (folder/'report-location.txt').write_text(str(report),encoding='utf-8')
    except Exception as exc:
        checks.append({'check':'Audit interruption','status':'FAIL','details':str(exc),'traceback':traceback.format_exc()})
        print(traceback.format_exc(),flush=True)
        if win:
            try:screen('99-failure')
            except Exception:pass
    finally:
        if process and process.poll() is None:
            try:win.close();process.wait(timeout=10)
            except Exception:process.terminate();process.wait(timeout=10)
        (folder/'checks.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding='utf-8')
    return 1 if any(c['status']=='FAIL' for c in checks) else 0

if __name__=='__main__':raise SystemExit(main())
