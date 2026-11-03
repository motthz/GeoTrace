"""Render a real exported HTML/PDF report for visual audit; never creates media."""
import argparse
import json
import os
from pathlib import Path
import sys

def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    folder=args.folder.resolve();report=Path((folder/'report-location.txt').read_text(encoding='utf-8'))
    from PySide6.QtCore import QTimer,QUrl,QSize
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtCore import Qt
    app=QApplication([]);view=QWebEngineView();view.resize(1100,850);view.show()
    outcome=[]
    def fail(message):
        outcome.append({'status':'FAIL','details':message});app.quit()
    def pdf():
        document=QPdfDocument(None);error=document.load(str(report/'report.pdf'))
        if error!=QPdfDocument.Error.None_:return fail('PDF load failed: '+str(error))
        pages=document.pageCount()
        if pages<1:return fail('PDF has no pages')
        for page in range(pages):
            rendered=document.render(page,QSize(900,1273))
            if rendered.isNull():return fail('PDF page failed: '+str(page))
            if not document.getAllText(page).text().strip():return fail('PDF page has no text: '+str(page))
            # PDF pages have transparent background; paint actual page content on white paper.
            canvas=QImage(rendered.size(),QImage.Format_RGB32);canvas.fill(Qt.white)
            painter=QPainter(canvas);painter.drawImage(0,0,rendered);painter.end()
            if page in (0,pages-1):canvas.save(str(folder/('report-pdf-'+str(page)+'.png')))
        if 'GeoTrace' not in document.getAllText(0).text():return fail('PDF text missing')
        outcome.append({'status':'PASS','details':'PDF opened and every page rendered','pages':pages})
        document.close();app.quit()
    def count_articles(count):
        expected=len(json.loads((report/'investigation.json').read_text(encoding='utf-8'))['records'])
        if count!=expected:return fail('HTML record count differs from JSON')
        outcome.append({'status':'PASS','details':'HTML rendered and record count matches JSON','records':count})
        view.page().runJavaScript("document.querySelector('article')?.scrollIntoView()")
        QTimer.singleShot(350,lambda:(view.grab().save(str(folder/'report-html-record.png')),pdf()))
    def ready(ok):
        if not ok:return fail('HTML load failed')
        def capture():
            view.grab().save(str(folder/'report-html.png'))
            view.page().runJavaScript("document.querySelectorAll('article').length",count_articles)
        QTimer.singleShot(500,capture)
    view.loadFinished.connect(ready);view.load(QUrl.fromLocalFile(str(report/'report.html')))
    QTimer.singleShot(45000,lambda:fail('Report audit deadline exceeded'))
    app.exec();view.close()
    (folder/'report-checks.json').write_text(json.dumps(outcome,indent=2),encoding='utf-8')
    print(json.dumps(outcome),flush=True)
    return 1 if not outcome or any(c['status']=='FAIL' for c in outcome) else 0

if __name__=='__main__':raise SystemExit(main())
