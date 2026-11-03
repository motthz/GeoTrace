"""Human-readable reports with lossless companion JSON and integrity manifest."""
import csv
import html
import json
import os
import tempfile
from pathlib import Path
from .core import duplicate_groups,sha256,canonical,now

LIMITATIONS='Discovery is bounded and incomplete. Provider failures are not zero results. Upload and publication times are not recording times. Unknown recording times remain unconfirmed. Footprint intersection is not exact location. No event occurrence is established by a query or result.'

def csv_value(value):
    if isinstance(value,str) and (value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n'))):
        return "'"+value
    return value

def _write(data,folder):
    esc=lambda v:html.escape(str(v),quote=True)
    (folder/'investigation.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['id','provider','title','url','media','recording','publication','upload','temporal_confidence','geographic_confidence','verification','license','sha256','discovered']
    with (folder/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        writer.writerows({key:csv_value(record.get(key)) for key in fields} for record in data['records'])
    body='<h1>GeoTrace investigation</h1><p>'+esc(LIMITATIONS)+'</p><h2>Parameters</h2><pre>'+esc(json.dumps(data['query'],indent=2,ensure_ascii=False))+'</pre><p>Executed: '+esc(data['created'])+'</p><h2>Source coverage</h2>'
    for name,status in data['coverage'].items():
        body+='<h3>'+esc(name)+' — '+esc(status['status'])+'</h3><p>'+esc(status.get('reason',''))+'</p><details><summary>Full source status</summary><pre>'+esc(json.dumps(status,indent=2))+'</pre></details>'
    body+='<h2>Discovered records ('+str(len(data['records']))+')</h2>'
    for r in data['records']:
        url=canonical(r['url'])
        body+='<article><h3>'+esc(r['title'])+'</h3><p><a href="'+esc(url)+'">Original source</a></p>'
        body+='<p>'+esc(' | '.join(f'{k}: {r.get(k) or "Unknown"}' for k in ('provider','media','recording','publication','upload','geographic_confidence','temporal_confidence','license','sha256')))+'</p>'
        body+='<details><summary>Original metadata and provenance</summary><pre>'+esc(json.dumps(r,indent=2,ensure_ascii=False))+'</pre></details></article>'
    body+='<h2>Related source groups</h2><pre>'+esc(duplicate_groups(data['records']))+'</pre><p>Lossless metadata: investigation.json. File integrity: manifest.json. Spreadsheet formula-like strings are escaped in CSV; originals remain in JSON.</p>'
    (folder/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GeoTrace report</title><style>body{font:15px system-ui;max-width:1000px;margin:32px auto;padding:16px;color:#182632}pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #bbb;padding:16px 0}a{overflow-wrap:anywhere}summary{cursor:pointer}</style>'+body+'</html>',encoding='utf-8')
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    import reportlab
    candidates=[Path(os.getenv('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf',Path(reportlab.__file__).parent/'fonts/Vera.ttf']
    font='Helvetica'
    for candidate in candidates:
        if candidate.is_file():
            if 'GeoTraceReport' not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont('GeoTraceReport',str(candidate)))
            font='GeoTraceReport'; break
    styles=getSampleStyleSheet()
    for style in styles.byName.values(): style.fontName=font
    story=[]
    def para(t): story.extend([Paragraph(esc(t),styles['BodyText']),Spacer(1,8)])
    para('GeoTrace — '+data['id']); para(LIMITATIONS); para('Parameters: '+json.dumps(data['query'],ensure_ascii=False)); para('Execution: '+data['created'])
    para('Source coverage')
    for name,status in data['coverage'].items(): para(name+': '+status['status']+' — '+status.get('reason',''))
    para('Discovered records: '+str(len(data['records'])))
    for r in data['records']:
        para(r['title'])
        story.append(Paragraph('<link href="'+esc(canonical(r['url']))+'">'+esc(r['url'])+'</link>',styles['BodyText']))
        for keys in [('provider','media','verification'),('recording','publication','upload'),('geographic_confidence','temporal_confidence'),('license','sha256')]:
            para(' | '.join(f'{key}: {r.get(key) or "Unknown"}' for key in keys))
    para('Evidence provenance: full unmodified provider metadata is preserved in companion investigation.json. SHA-256: '+sha256(folder/'investigation.json'))
    para('CSV formula-like text is escaped for spreadsheet safety; originals remain in JSON. See manifest.json for report file integrity.')
    SimpleDocTemplate(str(folder/'report.pdf'),title='GeoTrace investigation').build(story)
    manifest={'investigation':data['id'],'exported_at':now(),'files':{p.name:sha256(p) for p in folder.iterdir() if p.is_file()}}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

def export(data,folder):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    # Generate everything before replacing any existing report files.
    with tempfile.TemporaryDirectory(prefix='.geotrace-export-',dir=folder.parent) as temporary:
        staging=Path(temporary); _write(data,staging)
        # Publish the completion/integrity marker only after every referenced file exists.
        (folder/'manifest.json').unlink(missing_ok=True)
        for path in sorted(staging.iterdir(),key=lambda p:(p.name=='manifest.json',p.name)):
            os.replace(path,folder/path.name)
    return folder
