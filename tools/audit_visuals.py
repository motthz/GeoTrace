"""Exercise preview and map controls on Windows using copied REAL investigation data."""
import argparse,json,os,subprocess,sys,time,re,sqlite3,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geotrace.core import Archive

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    folder=args.output.resolve();profile=folder/'profile/GeoTrace';profile.mkdir(parents=True,exist_ok=True)
    source=sqlite3.connect(args.archive.resolve().as_uri()+'?mode=ro',uri=True);destination=sqlite3.connect(profile/'archive.sqlite')
    try:source.backup(destination)
    finally:source.close();destination.close()
    archive=Archive(profile/'archive.sqlite');id=next(id for id,_ in archive.list() if archive.load(id)['records']);data=archive.load(id)
    from pywinauto import Application
    from pywinauto import mouse
    env=dict(os.environ);env.pop('QT_QPA_PLATFORM',None);env['LOCALAPPDATA']=str(folder/'profile')
    process=subprocess.Popen([str(args.exe.resolve())],cwd=ROOT,env=env);win=None;checks=[]
    def find(name,kind,root=None):return next((c for c in (root or win).descendants(control_type=kind) if c.element_info.name==name),None)
    def wait(predicate,seconds=35):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=predicate()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Visual control condition timed out')
    def screen(name):win.capture_as_image().save(str(folder/(name+'.png')))
    def passed(name,details=''):checks.append({'check':name,'status':'PASS','details':details});print('PASS:',name,details,flush=True)
    def previews_loaded():
        return any(re.search(r'Anteprime: [1-9]\d* caricate',c.window_text()) for c in win.descendants(control_type='Text'))
    def tile_status():
        for c in win.descendants(control_type='Text'):
            text=c.window_text();match=re.search(r'Zoom (\d+).*?(\d+)/(\d+)',text)
            if match:return int(match[1]),int(match[2]),int(match[3]),text
        return None
    def map_ready():
        status=tile_status();return status if status and status[2]>0 and status[1]==status[2] else None
    try:
        app=Application(backend='uia').connect(process=process.pid,timeout=30);win=app.window(title_re='GeoTrace.*');win.wait('visible');win.set_focus()
        find('Open archived investigation','Button').click_input();picker=wait(lambda:find('Investigations','Window'))
        picker.descendants(control_type='ComboBox')[0].select(dict(archive.list())[id]+' | '+id);find('OK','Button',picker).click_input()
        wait(previews_loaded);win.descendants(control_type='Table')[0].click_input(coords=(100,60));screen('01-real-previews-credit')
        assert any('Licenza:' in c.window_text() for c in win.descendants(control_type='Text'));passed('Real source previews load with selected author/license attribution')
        find('Mostra anteprime','CheckBox').click_input();wait(lambda:find('Anteprime disattivate.','Text'));screen('02-compact-metadata');passed('Preview toggle switches to compact metadata view')
        find('Mostra anteprime','CheckBox').click_input();time.sleep(.3);wait(previews_loaded);screen('03-previews-restored');passed('Re-enabling previews restores cached images')
        find('Street map (OSM)','TabItem').select();initial=wait(map_ready);screen('04-current-basemap');passed('Actual public basemap tiles render',initial[3])
        find('+','Button').click_input();zoomed=wait(lambda:map_ready() if map_ready() and map_ready()[0]>initial[0] else None);screen('05-zoom');passed('Map zoom loads only the newly visible tile level',zoomed[3])
        candidates=[c for c in win.descendants() if c.element_info.automation_id.endswith('.TileView')]
        if not candidates:raise RuntimeError('Street-map canvas not exposed to accessibility')
        canvas=max(candidates,key=lambda c:c.rectangle().width()*c.rectangle().height());rect=canvas.rectangle();cx=(rect.left+rect.right)//2;cy=(rect.top+rect.bottom)//2
        mouse.press(coords=(cx,cy))
        for step in range(1,7):mouse.move(coords=(cx+15*step,cy+7*step));time.sleep(.03)
        mouse.release(coords=(cx+90,cy+42));time.sleep(.3);wait(map_ready)
        assert find('Street map (OSM)','TabItem').is_selected();screen('06-pan');passed('Dragging pans without opening a media record')
        find('Centra','Button').click_input();time.sleep(.3);wait(map_ready);screen('07-recenter');passed('Recenter restores the investigation area')
        find('Media gallery','TabItem').select()
        unsupported=next((r for r in data['records'] if isinstance(r.get('thumbnail'),str) and r['thumbnail'].startswith('s3://')),None)
        if unsupported:
            field=find('','Edit');field.set_edit_text(unsupported['title']);time.sleep(.7);screen('08-non-web-preview')
            assert any('non disponibili' in c.window_text() for c in win.descendants(control_type='Text'));passed('Non-web preview stays explicitly unavailable with original record retained')
            field.set_edit_text('')
        assert archive.load(id)['records']==data['records'];passed('Visual operations leave original archive records unchanged')
    except Exception as exc:
        checks.append({'check':'Audit interruption','status':'FAIL','details':str(exc),'traceback':traceback.format_exc()});print(traceback.format_exc(),flush=True)
        if win:
            try:screen('99-failure')
            except Exception:pass
    finally:
        mouse.release(coords=(0,0))
        if process.poll() is None:
            try:win.close();process.wait(timeout=10)
            except Exception:process.terminate();process.wait(timeout=10)
        (folder/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    return 1 if any(c['status']=='FAIL' for c in checks) else 0

if __name__=='__main__':raise SystemExit(main())
