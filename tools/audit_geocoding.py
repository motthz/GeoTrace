"""Real Windows user interactions for automatic place/timezone fields and errors."""
import argparse,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path);parser.add_argument('--output',type=Path,default=ROOT/'private/audit/geocoding');args=parser.parse_args()
    folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=True)
    from pywinauto import Application
    env=dict(os.environ);env.pop('QT_QPA_PLATFORM',None);env['LOCALAPPDATA']=str(folder/'profile')
    command=[str(args.exe.resolve())] if args.exe else [sys.executable,'-m','geotrace.app']
    process=subprocess.Popen(command,cwd=ROOT,env=env);checks=[];win=None
    def wait(check,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if check():return
            time.sleep(.15)
        raise TimeoutError('Geocoding user workflow timed out')
    def find(name,kind,root=None):
        results=[c for c in (root or win).descendants(control_type=kind) if c.element_info.name==name]
        return results[0] if results else None
    def edit(name,value):
        field=find(name,'Edit');field.set_edit_text(value);field.type_keys('{TAB}')
    def value(name):return find(name,'Edit').get_value()
    def screen(name,root=None):(root or win).capture_as_image().save(str(folder/(name+'.png')))
    def record(name):checks.append({'check':name,'status':'PASS'});print('PASS:',name,flush=True)
    def choose_if_needed():
        picker=find('OpenStreetMap / Nominatim','Window')
        if picker:
            screen('01-location-choice',picker)
            find('OK','Button',picker).click_input()
        return value('location')!='Roma' and value('lat')!='46.24645'
    try:
        app=Application(backend='uia').connect(process=process.pid,timeout=30);win=app.window(title_re='GeoTrace.*');win.wait('visible',timeout=30);win.set_focus()
        edit('location','Roma');wait(choose_if_needed)
        assert value('zone')=='Europe/Rome';screen('02-forward-place');record('Real location lookup, optional choice and automatic timezone')
        edit('lat','40,7128');edit('lon','-74,0060')
        wait(lambda:value('zone')=='America/New_York' and ',' not in value('lat') and '40.7128' not in value('location') and value('location')!='Roma')
        assert abs(float(value('lat'))-40.7128)<1e-9 and abs(float(value('lon'))+74.006)<1e-9
        screen('03-reverse-new-york');record('Rapid coordinate edits preserve final exact point and fill New York timezone')
        edit('location','GeoTraceAuditNoSuchPlace5D41402ABC')
        wait(lambda:find('GeoTrace','Window') is not None)
        error=find('GeoTrace','Window');screen('04-place-not-found',error);find('OK','Button',error).click_input()
        assert find('Start search','Button').is_enabled();record('Unknown location error is visible and recoverable')
        edit('location','Roma');wait(choose_if_needed)
        edit('start','25/10/2026 02:30');find('Start search','Button').click_input()
        wait(lambda:find('GeoTrace','Window') is not None)
        error=find('GeoTrace','Window');screen('05-dst-ambiguity',error)
        assert any('Ambiguous' in c.window_text() for c in error.descendants(control_type='Text'))
        find('OK','Button',error).click_input();record('Ambiguous DST recording interval blocked visibly')
        checkbox=find('Fuso orario automatico dalle coordinate','CheckBox');checkbox.click_input();edit('zone','UTC')
        assert value('zone')=='UTC';screen('06-manual-timezone');record('Manual IANA timezone override remains editable')
    except Exception as exc:
        checks.append({'check':'Audit interruption','status':'FAIL','details':str(exc),'traceback':traceback.format_exc()});print(traceback.format_exc(),flush=True)
        if win:
            try:screen('99-failure')
            except Exception:pass
    finally:
        if process.poll() is None:
            try:win.close();process.wait(timeout=10)
            except Exception:process.terminate();process.wait(timeout=10)
        (folder/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    return 1 if any(c['status']=='FAIL' for c in checks) else 0

if __name__=='__main__':raise SystemExit(main())
