import asyncio
import json
import os
import sys
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QDesktopServices, QColor, QPen, QFont, QFontDatabase
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QSpinBox,QPushButton,QTableWidget,QTableWidgetItem,QTabWidget,QTextBrowser,QFileDialog,QMessageBox,QGraphicsView,QGraphicsScene,QSplitter)
from .core import Archive,Query
from .providers import search,PROVIDERS,geocode
from .reports import export,LIMITATIONS

def data_dir(): return Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'GeoTrace'

class Worker(QThread):
    progress=Signal(str,str,int)
    done=Signal(str)
    failure=Signal(str)
    def __init__(self,archive,q,selected):
        super().__init__(); self.archive=archive; self.q=q; self.selected=selected; self.loop=None; self.task=None
        self.id=archive.create(q)
    def run(self):
        self.loop=asyncio.new_event_loop()
        self.task=self.loop.create_task(search(self.archive,self.q,self.progress.emit,self.selected,self.id))
        try: self.loop.run_until_complete(self.task)
        except asyncio.CancelledError: pass
        except Exception as e: self.failure.emit(str(e))
        finally: self.loop.close(); self.done.emit(self.id)
    def cancel(self):
        if self.loop and self.task: self.loop.call_soon_threadsafe(self.task.cancel)

class GeoWorker(QThread):
    done=Signal(object)
    failure=Signal(str)
    def __init__(self,text): super().__init__(); self.text=text
    def run(self):
        try: self.done.emit(asyncio.run(geocode(self.text)))
        except Exception as e: self.failure.emit(str(e))

class MapView(QGraphicsView):
    recordClicked=Signal(str)
    def wheelEvent(self,event):
        factor=1.3 if event.angleDelta().y()>0 else 1/1.3
        self.scale(factor,factor)
    def mouseDoubleClickEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if item and item.data(0): self.recordClicked.emit(item.data(0))
        super().mouseDoubleClickEvent(event)

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        if not QFontDatabase.families() and sys.platform=='win32':
            QFontDatabase.addApplicationFont(str(Path(os.getenv('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'))
            QApplication.instance().setFont(QFont('Segoe UI',10))
        self.setWindowTitle('GeoTrace — public media discovery'); self.resize(1450,900)
        self.archive=Archive(data_dir()/'archive.sqlite'); self.worker=None; self.current=None; self.records=[]
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        form=QFormLayout(); self.inputs={}
        defaults={'location':'Samolaco railway station, Italy','lat':'46.24645','lon':'9.42375','start':'2026-10-31T01:00:00','end':'2026-10-31T02:00:00','zone':'Europe/Rome','keywords':''}
        for key,value in defaults.items():
            edit=QLineEdit(value); self.inputs[key]=edit; form.addRow(key,edit)
        self.radius=QSpinBox(); self.radius.setRange(50,100000); self.radius.setValue(1000); form.addRow('Radius (m)',self.radius)
        self.mode=QComboBox(); self.mode.addItems(['QUICK','DEEP','EXTENDED']); form.addRow('Depth (bounded catalog limits)',self.mode)
        self.sources=QLineEdit(', '.join(p.cap.name for p in PROVIDERS)); form.addRow('Sources (comma separated)',self.sources)
        self.media=QLineEdit('image, video, satellite, article'); form.addRow('Media types',self.media)
        controls=QWidget(); controls.setLayout(form)
        controls.setMinimumWidth(430)
        self.tabs=QTabWidget(); split=QSplitter(); split.addWidget(controls); split.addWidget(self.tabs); split.setStretchFactor(1,3); split.setSizes([450,1000]); layout.addWidget(split)
        actions=QHBoxLayout(); layout.addLayout(actions)
        self.start=QPushButton('Start search'); self.start.clicked.connect(self.begin); actions.addWidget(self.start)
        self.locate=QPushButton('Geocode location'); self.locate.clicked.connect(self.locate_place); actions.addWidget(self.locate)
        self.cancel=QPushButton('Cancel'); self.cancel.clicked.connect(lambda:self.worker.cancel() if self.worker else None); actions.addWidget(self.cancel)
        save=QPushButton('Export HTML / PDF / CSV / JSON'); save.clicked.connect(self.export); actions.addWidget(save)
        reopen=QPushButton('Open archived investigation'); reopen.clicked.connect(self.reopen); actions.addWidget(reopen)
        self.filter=QLineEdit(); self.filter.setPlaceholderText('Filter results by title, source or confidence'); self.filter.textChanged.connect(self.filter_rows); layout.addWidget(self.filter)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(['Title','Source','Media','Recording','Upload / publication','Location','Time confidence']); self.table.cellDoubleClicked.connect(self.open_record); self.tabs.addTab(self.table,'Media gallery')
        self.scene=QGraphicsScene(); self.map=MapView(self.scene); self.map.setDragMode(QGraphicsView.ScrollHandDrag); self.map.recordClicked.connect(self.select_record); self.tabs.addTab(self.map,'Map (offline coordinates)')
        self.timeline=QTextBrowser(); self.tabs.addTab(self.timeline,'Timeline')
        self.coverage=QTextBrowser(); self.tabs.addTab(self.coverage,'Source coverage')
        self.details=QTextBrowser(); self.tabs.addTab(self.details,'Original metadata')
        self.table.itemSelectionChanged.connect(self.show_details)
        self.statusBar().showMessage('Ready. '+LIMITATIONS)
    def locate_place(self):
        self.locate.setEnabled(False); self.geo=GeoWorker(self.inputs['location'].text())
        self.geo.done.connect(self.located); self.geo.failure.connect(self.error)
        # One request at a time, plus one second cooldown; no autocomplete calls.
        from PySide6.QtCore import QTimer
        self.geo.finished.connect(lambda:QTimer.singleShot(1100,lambda:self.locate.setEnabled(True)))
        self.geo.start()
    def located(self,places):
        from PySide6.QtWidgets import QInputDialog
        if not places: self.error('No matching location'); return
        names=[p['display_name'] for p in places]
        name,ok=QInputDialog.getItem(self,'OpenStreetMap / Nominatim','Choose location',names,0,False)
        if ok:
            p=places[names.index(name)]; self.inputs['lat'].setText(p['lat']); self.inputs['lon'].setText(p['lon']); self.inputs['location'].setText(name)
    def select_record(self,id):
        for index,r in enumerate(self.records):
            if r['id']==id: self.table.selectRow(index); self.show_details(); self.tabs.setCurrentWidget(self.details); break
    def begin(self):
        try:
            values={k:v.text() for k,v in self.inputs.items()}; values['lat']=float(values['lat']); values['lon']=float(values['lon'])
            q=Query(**values,radius=self.radius.value(),mode=self.mode.currentText(),media=tuple(x.strip() for x in self.media.text().split(',')))
            selected=[x.strip() for x in self.sources.text().split(',')]
            unknown=set(selected)-{p.cap.name for p in PROVIDERS}
            if unknown: raise ValueError('Unknown active connectors: '+', '.join(unknown))
            self.worker=Worker(self.archive,q,selected); self.worker.progress.connect(self.progress); self.worker.done.connect(self.finished); self.worker.failure.connect(self.error)
            self.start.setEnabled(False); self.worker.start()
        except Exception as e: self.error(str(e))
    def progress(self,name,status,count):
        self.statusBar().showMessage(f'{name}: {status} ({count} records)'); self.render(self.worker.id)
    def finished(self,id): self.start.setEnabled(True); self.render(id); self.statusBar().showMessage('Search stopped. Inspect source coverage and uncertainties.')
    def render(self,id):
        self.current=id; data=self.archive.load(id); self.records=data['records']; self.table.setRowCount(len(self.records))
        for i,r in enumerate(self.records):
            values=[r['title'],r['provider'],r['media'],r['recording'] or 'Unknown',r['upload'] or r['publication'] or 'Unknown',r['geographic_confidence'],r['temporal_confidence']]
            for j,v in enumerate(values): self.table.setItem(i,j,QTableWidgetItem(str(v)))
        self.table.resizeColumnsToContents(); self.coverage.setPlainText(json.dumps(data['coverage'],indent=2)); self.filter_rows()
        events=[]
        for r in self.records:
            for key in ('recording','publication','upload'):
                if r.get(key): events.append((r[key],key,r['title'],r['temporal_confidence']))
        self.timeline.setPlainText('Discrete events only; no continuous coverage implied. Times below retain original offsets.\n\n'+'\n'.join(' | '.join(e) for e in sorted(events)))
        self.scene.clear(); self.scene.setSceneRect(-180,-90,360,180)
        self.scene.addRect(-180,-90,360,180,QPen(QColor('#667788')))
        q=data['query']; self.scene.addEllipse(q['lon']-.3,-q['lat']-.3,.6,.6,QPen(QColor('red')))
        dx=q['radius']/111320; import math
        self.scene.addEllipse(q['lon']-dx/max(.001,math.cos(math.radians(q['lat']))),-q['lat']-dx,2*dx/max(.001,math.cos(math.radians(q['lat']))),2*dx,QPen(QColor('red')))
        for r in self.records:
            if r['lat'] is not None and r['lon'] is not None:
                item=self.scene.addEllipse(r['lon']-.18,-r['lat']-.18,.36,.36,QPen(QColor('blue'))); item.setToolTip(r['title']); item.setData(0,r['id'])
            geometry=r['raw'].get('geometry') or {}
            if geometry.get('type')=='Polygon':
                from PySide6.QtGui import QPolygonF
                from PySide6.QtCore import QPointF
                polygon=QPolygonF([QPointF(p[0],-p[1]) for p in geometry['coordinates'][0]])
                item=self.scene.addPolygon(polygon,QPen(QColor('#698f99'))); item.setToolTip(r['title']); item.setData(0,r['id'])
        self.map.fitInView(self.scene.sceneRect(),Qt.KeepAspectRatio)
    def filter_rows(self):
        needle=self.filter.text().casefold()
        for i,r in enumerate(self.records): self.table.setRowHidden(i,needle not in json.dumps(r).casefold())
    def show_details(self):
        i=self.table.currentRow()
        if 0<=i<len(self.records): self.details.setPlainText(json.dumps(self.records[i],indent=2,ensure_ascii=False))
    def open_record(self,row,col): QDesktopServices.openUrl(QUrl(self.records[row]['url']))
    def reopen(self):
        from PySide6.QtWidgets import QInputDialog
        choices=[f'{created} | {id}' for id,created in self.archive.list()]
        if not choices: return
        choice,ok=QInputDialog.getItem(self,'Investigations','Select archive',choices,0,False)
        if ok: self.render(choice.split(' | ')[1])
    def export(self):
        if not self.current: return
        folder=QFileDialog.getExistingDirectory(self,'Export destination')
        if folder:
            try: export(self.archive.load(self.current),Path(folder)/self.current); self.statusBar().showMessage('Report exported')
            except Exception as e: self.error(str(e))
    def error(self,text): QMessageBox.warning(self,'GeoTrace',text)
    def closeEvent(self,event):
        if hasattr(self,'geo') and self.geo.isRunning(): event.ignore(); return
        if self.worker and self.worker.isRunning():
            self.worker.cancel(); event.ignore(); self.statusBar().showMessage('Cancelling search; close again after completion'); return
        event.accept()

def main():
    app=QApplication(sys.argv); app.setStyle('Fusion'); app.setFont(QFont('Segoe UI',10)); window=Window(); window.show(); sys.exit(app.exec())

if __name__=='__main__': main()
