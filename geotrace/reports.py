import csv
import html
import json
from pathlib import Path
from .core import duplicate_groups

LIMITATIONS='Discovery is bounded and incomplete. Provider failures are not zero results. Upload and publication times are not recording times. Unknown recording times remain unconfirmed. Footprint intersection is not exact location. No event occurrence is established by a query or result.'

def export(data, folder):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    (folder/'investigation.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['id','provider','title','url','media','recording','publication','upload','temporal_confidence','geographic_confidence','license','sha256']
    with (folder/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(data['records'])
    esc=lambda v:html.escape(str(v))
    body='<h1>GeoTrace investigation</h1><p>'+esc(LIMITATIONS)+'</p><h2>Parameters</h2><pre>'+esc(json.dumps(data['query'],indent=2))+'</pre><p>Executed: '+esc(data['created'])+'</p><h2>Source coverage</h2>'
    for name,status in data['coverage'].items(): body+='<h3>'+esc(name)+'</h3><pre>'+esc(json.dumps(status,indent=2))+'</pre>'
    body+='<h2>Discovered records</h2>'
    for r in data['records']:
        body+='<article><h3>'+esc(r['title'])+'</h3><a href="'+esc(r['url'])+'">Original source</a><pre>'+esc(json.dumps(r,indent=2,ensure_ascii=False))+'</pre></article>'
    body+='<h2>Related source groups</h2><pre>'+esc(duplicate_groups(data['records']))+'</pre>'
    (folder/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>GeoTrace report</title><style>body{font:15px system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #bbb}</style>'+body,encoding='utf-8')
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    styles=getSampleStyleSheet(); story=[]
    def para(t): story.extend([Paragraph(esc(t),styles['BodyText']),Spacer(1,8)])
    para('GeoTrace — '+data['id']); para(LIMITATIONS); para(json.dumps(data['query'])); para('Execution: '+data['created'])
    for name,status in data['coverage'].items(): para(name+': '+json.dumps(status))
    for r in data['records']: para(json.dumps(r,ensure_ascii=False))
    SimpleDocTemplate(str(folder/'report.pdf')).build(story)
    return folder
