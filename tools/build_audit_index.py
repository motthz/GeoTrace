"""Build a local, inspectable index of final audit evidence; no network publication."""
import argparse
import html
import json
from pathlib import Path
import sys
from urllib.parse import quote
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geotrace.core import sha256

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,default=ROOT/'private/audit');args=parser.parse_args();base=args.folder.resolve()
    runs=[('source-final','App dai sorgenti'),('geocoding-source-pass','Geocodifica dai sorgenti'),('packaged-final','Eseguibile Windows'),('geocoding-packaged-final','Geocodifica nell’eseguibile')]
    esc=lambda value:html.escape(str(value),quote=True)
    tests=ET.parse(base/'tests-final.xml').findall('.//testcase')
    assert tests and not any(t.find('failure') is not None or t.find('error') is not None for t in tests)
    checks_total=0;screens=0;content='';files={}
    for directory,title in runs:
        folder=base/directory;checks=json.loads((folder/'checks.json').read_text(encoding='utf-8'))
        assert checks and all(c['status']=='PASS' for c in checks),directory+' has failed or missing checks'
        checks_total+=len(checks)
        content+='<section><h2>'+esc(title)+'</h2><details><summary>'+str(len(checks))+' controlli riusciti</summary><ul>'+''.join('<li>'+esc(c.get('check',c.get('details','')))+' — '+esc(c.get('details',''))+'</li>' for c in checks)+'</ul></details>'
        report_location=folder/'report-location.txt'
        if report_location.exists():
            report=Path(report_location.read_text(encoding='utf-8')).resolve()
            assert report.is_relative_to(base)
            report_checks=json.loads((folder/'report-checks.json').read_text(encoding='utf-8'))
            assert report_checks and all(c['status']=='PASS' for c in report_checks)
            checks_total+=len(report_checks)
            content+='<p>Report controllati: '+', '.join('<a href="'+quote(str((report/name).relative_to(base)).replace('\\','/'))+'">'+esc(name)+'</a>' for name in ('report.html','report.pdf','results.csv','investigation.json','manifest.json'))+'</p>'
        content+='<div class="gallery">'
        for picture in sorted(folder.glob('*.png')):
            href=quote(str(picture.relative_to(base)).replace('\\','/'));screens+=1
            files[str(picture.relative_to(base)).replace('\\','/')]=sha256(picture)
            content+='<figure data-title="'+esc(title+' '+picture.stem)+'"><a href="'+href+'"><img loading="lazy" src="'+href+'" alt="'+esc(picture.stem)+'"></a><figcaption>'+esc(picture.stem)+'</figcaption></figure>'
        content+='</div></section>'
    (base/'evidence-manifest.json').write_text(json.dumps({'automated_tests':len(tests),'native_and_render_checks':checks_total,'screenshots':screens,'sha256':files},indent=2),encoding='utf-8')
    page='''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GeoTrace — Audit verificabile</title><style>body{font:16px system-ui;color:#19333d;background:#f5f8fa;max-width:1400px;margin:auto;padding:30px}h1{font-size:32px}section{margin:32px 0}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:18px}figure{margin:0;background:white;border:1px solid #cbd6dc;border-radius:6px;overflow:hidden}figure[hidden]{display:none}img{display:block;width:100%;max-height:320px;object-fit:contain;background:#e7edef}figcaption{padding:12px;overflow-wrap:anywhere}a{color:#075f88}input{font:inherit;padding:10px;width:min(600px,90%)}.summary{padding:16px;background:white;border-left:4px solid #147361}details{padding:12px;background:white}li{margin-bottom:8px}</style><h1>GeoTrace 0.1.3 — Audit verificabile</h1>'''
    page+='<p>Conclusione dell’audit: 3 novembre 2026. Evidenze locali, separate dal repository pubblico e dalle indagini personali.</p><div class="summary"><strong>'+str(len(tests))+' test automatici superati · '+str(checks_total)+' controlli di flusso/rendering superati · '+str(screens)+' screenshot</strong></div>'
    page+='<p>Le finestre sono state azionate tramite mouse e tastiera su Windows; i risultati provengono da API reali. Le sei schede sono state controllate anche visivamente. I PDF sono stati renderizzati pagina per pagina e gli export confrontati con l’archivio e il manifesto SHA-256.</p><p><strong>Limiti:</strong> mappa a coordinate senza base stradale; galleria di metadati senza anteprime; AI e download con coda non implementati; fonti social/video soggette ad autorizzazione. I test non garantiscono disponibilità futura delle API, copertura esaustiva né compatibilità con ogni altro PC.</p><p><a href="evidence-manifest.json">Manifesto degli screenshot</a> · <a href="tests-final.xml">Risultati test JUnit</a></p><input id="filter" placeholder="Filtra screenshot: map, timeline, metadata, export…" aria-label="Filtra screenshot">'
    page+=content+'<script>document.getElementById("filter").addEventListener("input",function(){const q=this.value.toLowerCase();document.querySelectorAll("figure").forEach(f=>f.hidden=!f.dataset.title.toLowerCase().includes(q))})</script></html>'
    (base/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'tests':len(tests),'checks':checks_total,'screenshots':screens,'index':str(base/'index.html')}))

if __name__=='__main__':main()
