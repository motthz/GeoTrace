import asyncio
import json
import os
import sys
import html
from datetime import datetime, timedelta
import time
import threading
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QDesktopServices, QColor, QPen, QFont, QFontDatabase,QPixmap,QIcon,QPainter
from PySide6.QtCore import QUrl,QSize,QEvent
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QSpinBox,QPushButton,QTableWidget,QTableWidgetItem,QTabWidget,QTextBrowser,QFileDialog,QMessageBox,QGraphicsView,QGraphicsScene,QSplitter,QCheckBox,QLabel,QScrollArea,QGridLayout,QAbstractItemView)
from .core import Archive,Query,data_dir
from .providers import search,PROVIDERS,geocode
from .reports import export,LIMITATIONS
from .images import ImageBroker,image_url_allowed,preview_credit
from .basemap import BasemapPanel

def map_pen(color):
    pen=QPen(QColor(color)); pen.setCosmetic(True); return pen

def map_longitude(longitude,center):
    return center+(longitude-center+180)%360-180

def display_time(stamp,zone):
    if not stamp:return 'Unknown'
    try:
        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('Offset unknown')
        return parsed.astimezone(ZoneInfo(zone)).isoformat()
    except (ValueError,KeyError,AttributeError,TypeError):return str(stamp)+' (original; time unconfirmed)'

class Worker(QThread):
    progress=Signal(str,str,int)
    done=Signal(str)
    failure=Signal(str)
    def __init__(self,archive,q,selected):
        super().__init__(); self.archive=archive; self.q=q; self.selected=selected; self.loop=None; self.task=None
        self.id=archive.create(q)
        self.cancelled=threading.Event()
    def run(self):
        self.loop=asyncio.new_event_loop()
        self.task=self.loop.create_task(search(self.archive,self.q,self.progress.emit,self.selected,self.id))
        if self.cancelled.is_set():
            self.archive.status(self.id,'Search coordinator',status='ERROR',reason='Cancelled before provider startup')
            self.task.cancel()
        try: self.loop.run_until_complete(self.task)
        except asyncio.CancelledError: pass
        except Exception as e: self.failure.emit(str(e))
        finally: self.loop.close(); self.done.emit(self.id)
    def cancel(self):
        self.cancelled.set()
        if self.loop and self.task and not self.loop.is_closed():
            try:self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:pass

class GeoWorker(QThread):
    done=Signal(object)
    failure=Signal(str)
    def __init__(self,text,reverse=False): super().__init__(); self.text=text; self.reverse=reverse
    def run(self):
        try: self.done.emit(asyncio.run(geocode(self.text,self.reverse)))
        except Exception as e: self.failure.emit(str(e))

class MapView(QGraphicsView):
    recordClicked=Signal(str)
    def wheelEvent(self,event):
        factor=1.3 if event.angleDelta().y()>0 else 1/1.3
        if .1<self.transform().m11()*factor<1e8: self.scale(factor,factor)
    def mouseReleaseEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        moved=(event.position().toPoint()-getattr(self,'press_position',event.position().toPoint())).manhattanLength()>5
        if not moved and item and item.data(0): self.recordClicked.emit(item.data(0))
        super().mouseReleaseEvent(event)
    def mousePressEvent(self,event):
        self.press_position=event.position().toPoint();super().mousePressEvent(event)
    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        painter.save();painter.resetTransform()
        from PySide6.QtCore import QRectF
        panel=QRectF(6,6,max(0,self.viewport().width()-12),55)
        painter.fillRect(panel,QColor(255,255,255,225));painter.setPen(QColor('#243b46'))
        painter.drawText(panel.adjusted(6,2,-6,-2),Qt.AlignLeft|Qt.TextWordWrap,'Offline coordinate map — no street basemap. Red: search area; blue: provider coordinates; gray: satellite footprints. Click for metadata; drag to pan; wheel to zoom.')
        painter.restore()
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
        self.setWindowTitle('GeoTrace — public media discovery')
        available=self.screen().availableGeometry()
        self.resize(min(1450,available.width()-40),min(900,available.height()-60))
        self.archive=Archive(data_dir()/'archive.sqlite'); self.worker=None; self.current=None; self.records=[]
        self.images=ImageBroker(self);self.preview_states={}
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(100);self.preview_timer.timeout.connect(self.load_visible_previews)
        self.resolved_location='Samolaco railway station, Italy'; self.pending_search=False
        self.resolved_coords=('46.24645','9.42375'); self.geo_snapshot=None; self.geo_next=0; self.applying_fields=False
        self.geo_refresh_pending=False; self.choosing_location=False
        self.date_snapshot=('2026-10-31T01:00:00','2026-10-31T02:00:00')
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        form=QFormLayout(); self.inputs={}
        defaults={'location':'Samolaco railway station, Italy','lat':'46.24645','lon':'9.42375','start':'2026-10-31T01:00:00','end':'2026-10-31T02:00:00','zone':'Europe/Rome','keywords':''}
        for key,value in defaults.items():
            edit=QLineEdit(value); edit.setObjectName('field_'+key); edit.setAccessibleName(key); self.inputs[key]=edit; form.addRow(key,edit)
        self.auto_zone=QCheckBox('Fuso orario automatico dalle coordinate'); self.auto_zone.setChecked(True)
        self.inputs['zone'].setReadOnly(True); self.auto_zone.toggled.connect(self.zone_mode); form.addRow(self.auto_zone)
        self.field_status=QLabel('Luogo e coordinate sincronizzati. Le date indicano ora locale.'); self.field_status.setWordWrap(True); form.addRow(self.field_status)
        self.inputs['location'].editingFinished.connect(self.auto_location)
        for key in ('lat','lon'): self.inputs[key].editingFinished.connect(self.auto_coordinates)
        for key in ('start','end'): self.inputs[key].editingFinished.connect(lambda key=key:self.normalize_dates(key))
        self.radius=QSpinBox(); self.radius.setRange(50,100000); self.radius.setValue(1000); form.addRow('Radius (m)',self.radius)
        self.mode=QComboBox(); self.mode.addItems(['QUICK','DEEP','EXTENDED']); form.addRow('Depth (bounded catalog limits)',self.mode)
        self.sources=QLineEdit(', '.join(p.cap.name for p in PROVIDERS)); form.addRow('Sources (comma separated)',self.sources)
        self.media=QLineEdit('image, video, satellite, article'); form.addRow('Media types',self.media)
        self.sources.setReadOnly(True); self.media.setReadOnly(True)
        self.source_checks={}; self.media_checks={}
        for names,target,label in [([p.cap.name for p in PROVIDERS],self.source_checks,'Fonti'),(['image','video','satellite','article'],self.media_checks,'Media')]:
            box=QWidget(); row=QVBoxLayout(box); row.setContentsMargins(0,0,0,0)
            for name in names:
                check=QCheckBox(name); check.setChecked(True); target[name]=check; row.addWidget(check); check.toggled.connect(self.sync_choices)
            form.addRow(label,box)
        controls=QWidget(); controls.setLayout(form)
        controls.setMinimumWidth(430)
        self.controls=controls
        scroller=QScrollArea(); scroller.setWidgetResizable(True); scroller.setWidget(controls); scroller.setMinimumWidth(260)
        self.tabs=QTabWidget(); split=QSplitter(); split.addWidget(scroller); split.addWidget(self.tabs); split.setStretchFactor(1,3); split.setSizes([450,1000]); layout.addWidget(split)
        self.tabs.setUsesScrollButtons(True)
        actions=QGridLayout(); layout.addLayout(actions)
        self.start=QPushButton('Start search'); self.start.clicked.connect(self.begin); actions.addWidget(self.start,0,0)
        self.locate=QPushButton('Geocode location'); self.locate.clicked.connect(self.locate_place); actions.addWidget(self.locate,0,1)
        self.cancel=QPushButton('Cancel'); self.cancel.setEnabled(False); self.cancel.clicked.connect(lambda:self.worker.cancel() if self.worker else None); actions.addWidget(self.cancel,0,2)
        self.save=QPushButton('Export HTML / PDF / CSV / JSON'); self.save.setEnabled(False); self.save.clicked.connect(self.export); actions.addWidget(self.save,1,0,1,2)
        self.reopen_button=QPushButton('Open archived investigation'); self.reopen_button.clicked.connect(self.reopen); actions.addWidget(self.reopen_button,1,2)
        self.filter=QLineEdit(); self.filter.setPlaceholderText('Filter results by title, source or confidence'); self.filter.textChanged.connect(self.filter_rows); layout.addWidget(self.filter)
        self.gallery_page=QWidget();gallery_layout=QVBoxLayout(self.gallery_page);gallery_bar=QHBoxLayout();gallery_layout.addLayout(gallery_bar)
        self.previews_enabled=QCheckBox('Mostra anteprime');self.previews_enabled.setChecked(True);self.previews_enabled.toggled.connect(self.toggle_previews);gallery_bar.addWidget(self.previews_enabled)
        self.preview_summary=QLabel('Anteprime delle fonti; non confermano la data o il luogo.');self.preview_summary.setWordWrap(True);gallery_bar.addWidget(self.preview_summary,1)
        retry=QPushButton('Riprova anteprime');retry.clicked.connect(self.retry_previews);gallery_bar.addWidget(retry)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(['Title','Source','Media','Recording','Upload / publication','Location','Time confidence']); self.table.cellDoubleClicked.connect(self.open_record);gallery_layout.addWidget(self.table);self.tabs.addTab(self.gallery_page,'Media gallery')
        self.gallery_credit=QLabel('Seleziona un risultato per attribuzione, licenza e fonte originale.');self.gallery_credit.setWordWrap(True);self.gallery_credit.setOpenExternalLinks(True);gallery_layout.addWidget(self.gallery_credit)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        self.table.setIconSize(QSize(120,88));self.table.verticalHeader().setDefaultSectionSize(100)
        self.table.viewport().installEventFilter(self)
        self.table.verticalScrollBar().valueChanged.connect(lambda:self.preview_timer.start())
        self.images.ready.connect(self.preview_ready)
        self.street=BasemapPanel(self.images,self);self.street.recordClicked.connect(self.select_record);self.tabs.addTab(self.street,'Street map (OSM)')
        self.scene=QGraphicsScene(); self.map=MapView(self.scene); self.map.setDragMode(QGraphicsView.ScrollHandDrag); self.map.recordClicked.connect(self.select_record); self.tabs.addTab(self.map,'Map (offline coordinates)')
        self.map.setToolTip('Offline longitude/latitude plot. Red: search area. Blue: provider coordinates. Gray: catalog footprints. Click a feature for metadata; wheel to zoom, drag to pan. No street basemap.')
        self.timeline=QTextBrowser(); self.tabs.addTab(self.timeline,'Timeline')
        self.timeline.setPlainText('Start a search or open an investigation to view discrete timestamp events. Unknown recording times are not plotted as recording events.')
        self.coverage=QTextBrowser(); self.tabs.addTab(self.coverage,'Source coverage')
        self.coverage.setPlainText('Start a search or open an investigation to inspect source status and limitations. Restricted providers are not searched automatically.')
        self.details=QTextBrowser(); self.tabs.addTab(self.details,'Original metadata')
        self.details.setPlainText('Select a result or click a map feature after a search to inspect original metadata.')
        self.links=QTextBrowser(); self.links.setOpenExternalLinks(True); self.tabs.addTab(self.links,'Public search links')
        self.links.setPlainText('Public platform search links are generated from the saved investigation parameters after a search starts.')
        self.scene.addText('Start a search or open an investigation to display its geographic area.')
        self.table.itemSelectionChanged.connect(self.show_details)
        self.tabs.currentChanged.connect(lambda:self.preview_timer.start())
        self.statusBar().showMessage('Ready. '+LIMITATIONS)
    def eventFilter(self,obj,event):
        if obj is self.table.viewport() and event.type() in (QEvent.Resize,QEvent.Show):self.preview_timer.start()
        return super().eventFilter(obj,event)
    def preview_icon(self,text):
        pixmap=QPixmap(120,88);pixmap.fill(QColor('#edf2f4'));painter=QPainter(pixmap);painter.setPen(QColor('#536875'));painter.drawText(pixmap.rect().adjusted(4,4,-4,-4),Qt.AlignCenter|Qt.TextWordWrap,text);painter.end();return QIcon(pixmap)
    def toggle_previews(self,enabled):
        self.table.verticalHeader().setDefaultSectionSize(100 if enabled else 32)
        if not enabled:
            self.images.keep_pending('preview',[])
            for row in range(self.table.rowCount()):self.table.item(row,0).setIcon(QIcon())
        self.preview_timer.start();self.update_preview_summary()
    def retry_previews(self):self.images.retry_errors();self.preview_timer.start()
    def update_preview_summary(self):
        if not self.previews_enabled.isChecked():self.preview_summary.setText('Anteprime disattivate.');return
        states=[self.preview_states.get(r['id']) for r in self.records]
        self.preview_summary.setText(f"Anteprime: {states.count('loaded')} caricate · {states.count('error')+states.count('absent')} non disponibili. Data e luogo restano da verificare.")
    def set_preview(self,row,image,error=''):
        if not 0<=row<len(self.records):return
        item=self.table.item(row,0)
        if item is None:return
        if not image.isNull():item.setIcon(QIcon(QPixmap.fromImage(image)))
        else:item.setIcon(self.preview_icon('Anteprima non disponibile' if error else 'Caricamento…'))
        self.preview_states[self.records[row]['id']]='error' if error else 'loaded' if not image.isNull() else 'loading'
        text=self.records[row]['title']+'\nAnteprima della fonte; non conferma data o luogo.\n'+preview_credit(self.records[row])+'\n'+(error or '')
        item.setToolTip(html.escape(text).replace('\n','<br>'))
        self.update_preview_summary()
    def load_visible_previews(self):
        if not self.table.isVisible() or not self.previews_enabled.isChecked():self.images.keep_pending('preview',[]);return
        urls=[]
        for row,r in enumerate(self.records):
            if self.table.isRowHidden(row):continue
            y=self.table.rowViewportPosition(row)
            if y+self.table.rowHeight(row)<0 or y>self.table.viewport().height():continue
            url=r.get('thumbnail')
            if not url:continue
            if not isinstance(url,str):
                from PySide6.QtGui import QImage
                self.set_preview(row,QImage(),'URL anteprima non valido');continue
            urls.append(url);self.images.request(url,'preview');image,error=self.images.result(url);self.set_preview(row,image,error)
        self.images.keep_pending('preview',urls)
    def preview_ready(self,url,image,error):
        if not self.previews_enabled.isChecked() or not image_url_allowed(url):return
        for row,r in enumerate(self.records):
            if r.get('thumbnail')==url:self.set_preview(row,image,error)
    def locate_place(self):
        if self.worker and self.worker.isRunning(): return
        if hasattr(self,'geo') and self.geo.isRunning(): self.geo_refresh_pending=True; return
        if time.monotonic()<self.geo_next:
            QTimer.singleShot(int((self.geo_next-time.monotonic())*1000)+10,self.locate_place); return
        reverse=self.coords()!=self.resolved_coords and self.inputs['location'].text().strip()==self.resolved_location
        self.geo_snapshot=(self.inputs['location'].text().strip(),self.coords(),reverse)
        text=','.join(self.coords()) if reverse else self.geo_snapshot[0]
        self.locate.setEnabled(False); self.geo=GeoWorker(text,reverse)
        self.geo.done.connect(self.located); self.geo.failure.connect(self.geo_error)
        self.geo_next=time.monotonic()+1.1
        self.geo.finished.connect(self.geo_finished)
        self.geo.start()
    def geo_finished(self):
        if self.choosing_location:
            QTimer.singleShot(100,self.geo_finished);return
        QTimer.singleShot(1100,lambda:self.locate.setEnabled(not(self.worker and self.worker.isRunning())))
        if self.geo_refresh_pending:
            self.geo_refresh_pending=False;QTimer.singleShot(0,self.locate_place)
        elif self.pending_search:
            self.pending_search=False; QTimer.singleShot(0,self.begin)
    def coords(self): return tuple(self.inputs[k].text().strip().replace(',','.') for k in ('lat','lon'))
    def sync_choices(self):
        self.sources.setText(', '.join(n for n,c in self.source_checks.items() if c.isChecked()))
        self.media.setText(', '.join(n for n,c in self.media_checks.items() if c.isChecked()))
    def set_search_running(self,running):
        self.controls.setEnabled(not running); self.start.setEnabled(not running); self.cancel.setEnabled(running)
        self.reopen_button.setEnabled(not running); self.locate.setEnabled(not running)
    def zone_mode(self,automatic):
        self.inputs['zone'].setReadOnly(automatic)
        if automatic: self.fill_zone()
    def fill_zone(self):
        if not self.auto_zone.isChecked(): return
        from tzfpy import get_tzs
        try:
            lat,lon=map(float,self.coords()); zones=get_tzs(lon,lat)
            zone=zones[0] if len(zones)==1 else ''
            if zone: ZoneInfo(zone)
            self.inputs['zone'].setText(zone)
            if not zone: self.field_status.setText('Fuso incerto o confine: disattiva il fuso automatico e seleziona una zona IANA.')
        except (ValueError,KeyError): self.inputs['zone'].clear()
    def auto_location(self):
        if not self.applying_fields and self.inputs['location'].text().strip()!=self.resolved_location:
            self.field_status.setText('Risoluzione del luogo in corso…'); self.locate_place()
    def auto_coordinates(self):
        if self.applying_fields or self.coords()==self.resolved_coords: return
        try:
            lat,lon=map(float,self.coords())
            if not (-90<=lat<=90 and -180<=lon<=180): raise ValueError()
        except ValueError:
            self.pending_search=False; self.start.setEnabled(True)
            self.field_status.setText('Coordinate non valide: latitudine -90…90, longitudine -180…180.'); return
        # Explicit coordinates are authoritative; never snap them to a nearby place centroid.
        self.inputs['lat'].setText(str(lat)); self.inputs['lon'].setText(str(lon))
        self.resolved_location=f'{lat}, {lon}'; self.inputs['location'].setText(self.resolved_location)
        self.fill_zone(); self.field_status.setText('Coordinate aggiornate; recupero del nome del luogo…'); self.locate_place()
    @staticmethod
    def parse_date(text):
        text=text.strip()
        try: return datetime.fromisoformat(text.replace('Z','+00:00'))
        except ValueError:
            for fmt in ('%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M','%d/%m/%Y'):
                try:return datetime.strptime(text,fmt)
                except ValueError:pass
            raise ValueError('Data non valida: usa AAAA-MM-GG HH:MM oppure GG/MM/AAAA HH:MM.')
    def normalize_dates(self,changed):
        try:
            start=self.parse_date(self.inputs['start'].text()); end=self.parse_date(self.inputs['end'].text())
            if changed=='start' and start.isoformat()!=self.date_snapshot[0]:
                previous_start,previous_end=map(datetime.fromisoformat,self.date_snapshot)
                duration=previous_end-previous_start
                if duration.total_seconds()<=0: duration=timedelta(hours=1)
                end=start+duration
                self.field_status.setText('Fine aggiornata automaticamente mantenendo la durata precedente.')
            if start.tzinfo or end.tzinfo:
                raise ValueError('Inserisci le ore locali senza offset; il campo fuso orario gestisce la conversione UTC.')
            if end<=start: raise ValueError('La fine deve essere successiva all’inizio.')
            self.inputs['start'].setText(start.isoformat(timespec='seconds')); self.inputs['end'].setText(end.isoformat(timespec='seconds'))
            self.date_snapshot=(self.inputs['start'].text(),self.inputs['end'].text())
            return True
        except (ValueError,TypeError) as exc:
            self.field_status.setText(str(exc)); return False
    def geo_error(self,text):
        if self.geo_snapshot and (self.coords()!=self.geo_snapshot[1] or self.inputs['location'].text().strip()!=self.geo_snapshot[0]):
            self.field_status.setText('Errore di una richiesta precedente; i nuovi campi non sono stati modificati.');return
        if self.geo_snapshot and self.geo_snapshot[2] and self.coords()==self.geo_snapshot[1]:
            self.resolved_coords=self.coords(); self.fill_zone()
            self.field_status.setText('Nome del luogo non disponibile: uso delle coordinate esatte.')
            pending=self.pending_search; self.pending_search=False
            if pending:self.pending_search=True
        else:self.error(text)
    def located(self,places):
        from PySide6.QtWidgets import QInputDialog
        if self.geo_snapshot:
            label,coords,reverse=self.geo_snapshot
            if self.inputs['location'].text().strip()!=label or self.coords()!=coords:
                if not self.geo_refresh_pending:self.pending_search=False;self.start.setEnabled(True)
                self.field_status.setText('Campi modificati durante la richiesta. Sincronizza i nuovi valori prima di cercare.'); return
            if reverse:
                if places.get('display_name'):
                    self.inputs['location'].setText(places['display_name']); self.resolved_location=places['display_name']
                self.resolved_coords=self.coords(); self.fill_zone()
                self.field_status.setText('Coordinate esatte, nome del luogo e fuso sincronizzati.')
                pending=self.pending_search; self.pending_search=False; self.start.setEnabled(True)
                if pending:self.pending_search=True
                return
        if not places: self.pending_search=False; self.start.setEnabled(True); self.error('No matching location. Enter coordinates or try a more precise location.'); return
        names=[p['display_name'] for p in places]
        self.choosing_location=True
        try:name,ok=(names[0],True) if len(names)==1 else QInputDialog.getItem(self,'OpenStreetMap / Nominatim','Choose location',names,0,False)
        finally:self.choosing_location=False
        if ok:
            p=places[names.index(name)]; self.inputs['lat'].setText(p['lat']); self.inputs['lon'].setText(p['lon']); self.inputs['location'].setText(name)
            self.resolved_location=name
            self.resolved_coords=self.coords(); self.fill_zone(); self.field_status.setText('Luogo, coordinate e fuso sincronizzati.')
        pending=self.pending_search; self.pending_search=False; self.start.setEnabled(True)
        if ok and pending:self.pending_search=True
    def select_record(self,id):
        for index,r in enumerate(self.records):
            if r['id']==id:
                if self.table.isRowHidden(index):self.filter.clear()
                self.table.selectRow(index);self.show_details();self.tabs.setCurrentWidget(self.details);break
    def begin(self):
        if self.worker and self.worker.isRunning(): return
        if not self.normalize_dates('end'): return
        if hasattr(self,'geo') and self.geo.isRunning():
            self.pending_search=True; self.start.setEnabled(False); return
        if self.coords()!=self.resolved_coords and self.inputs['location'].text().strip()==self.resolved_location:
            self.pending_search=True; self.start.setEnabled(False); self.auto_coordinates(); return
        if self.inputs['location'].text().strip()!=self.resolved_location:
            self.pending_search=True; self.start.setEnabled(False); self.locate_place(); return
        try:
            self.fill_zone(); self.sync_choices()
            values={k:v.text() for k,v in self.inputs.items()}; values['lat']=float(values['lat']); values['lon']=float(values['lon'])
            q=Query(**values,radius=self.radius.value(),mode=self.mode.currentText(),media=tuple(x.strip() for x in self.media.text().split(',')))
            selected=[x.strip() for x in self.sources.text().split(',')]
            if not any(c.isChecked() for c in self.source_checks.values()): raise ValueError('Seleziona almeno una fonte.')
            if not any(c.isChecked() for c in self.media_checks.values()): raise ValueError('Seleziona almeno un tipo di media.')
            if not any(p.cap.name in selected and set(q.media).intersection(p.cap.media) for p in PROVIDERS): raise ValueError('Le fonti selezionate non supportano i tipi di media scelti.')
            unknown=set(selected)-{p.cap.name for p in PROVIDERS}
            if unknown: raise ValueError('Unknown active connectors: '+', '.join(unknown))
            self.worker=Worker(self.archive,q,selected); self.worker.progress.connect(self.progress); self.worker.finished.connect(lambda worker=self.worker:self.finished(worker.id)); self.worker.failure.connect(self.error)
            self.set_search_running(True); self.current=self.worker.id; self.render(self.current); self.worker.start()
        except Exception as e:
            message=str(e)
            if 'Ambiguous or nonexistent local time' in message:
                message='Ambiguous or nonexistent local time. Disattiva il fuso automatico, imposta UTC e inserisci le ore in UTC; oppure scegli un orario locale non ambiguo.'
            self.error(message)
    def progress(self,name,status,count):
        self.statusBar().showMessage(f'{name}: {status} ({count} records)'); self.render(self.worker.id)
    def finished(self,id):
        self.set_search_running(False); self.render(id)
        prefix='Search cancelled. ' if self.worker and self.worker.cancelled.is_set() else ''
        self.statusBar().showMessage(prefix+f'{len(self.records)} records saved. Unknown recording dates are unconfirmed. See Source coverage for failures and Public search links for other sources.')
    def render(self,id):
        selected_id=self.records[self.table.currentRow()]['id'] if 0<=self.table.currentRow()<len(self.records) else None
        self.current=id; self.save.setEnabled(True); data=self.archive.load(id)
        self.records=sorted(data['records'],key=lambda r:(0 if isinstance(r.get('thumbnail'),str) and r['thumbnail'].startswith('https://') else 1,0 if r['media'] in ('image','video') else 1))
        self.table.blockSignals(True); self.table.setRowCount(len(self.records))
        for i,r in enumerate(self.records):
            values=[r['title'],r['provider'],r['media'],display_time(r['recording'],data['query']['zone']),display_time(r['upload'] or r['publication'],data['query']['zone']),r['geographic_confidence'],r['temporal_confidence']]
            for j,v in enumerate(values):
                item=QTableWidgetItem(str(v));item.setToolTip(str(v));self.table.setItem(i,j,item)
            if self.previews_enabled.isChecked():self.table.item(i,0).setIcon(self.preview_icon('Anteprima della fonte' if r.get('thumbnail') else 'Nessuna anteprima'))
            if not r.get('thumbnail'):self.preview_states[r['id']]='absent'
        self.table.blockSignals(False)
        self.update_preview_summary()
        self.table.resizeColumnsToContents(); self.table.setColumnWidth(0,360); self.filter_rows()
        if selected_id:
            for i,r in enumerate(self.records):
                if r['id']==selected_id and not self.table.isRowHidden(i): self.table.selectRow(i); break
        self.show_details()
        rows=''.join('<tr><td>'+html.escape(name)+'</td><td>'+html.escape(s['status'])+'</td><td>'+str(s.get('count','—'))+'</td><td>'+html.escape(s.get('reason',''))+'</td></tr>' for name,s in data['coverage'].items())
        self.coverage.setHtml('<h2>Actual provider coverage</h2><p>A failed source is not an empty search.</p><table border="1" cellpadding="7"><tr><th>Provider</th><th>Status</th><th>Records</th><th>Details / limitations</th></tr>'+rows+'</table>')
        events=[]
        for r in self.records:
            for key in ('recording','publication','upload'):
                if r.get(key):
                    instant=float('inf')
                    try:
                        dt=datetime.fromisoformat(r[key].replace('Z','+00:00'))
                        if dt.tzinfo is None: raise ValueError('Unknown offset')
                        stamp=dt.astimezone(ZoneInfo(data['query']['zone'])).isoformat()
                        instant=dt.timestamp()
                    except (ValueError,KeyError,TypeError,AttributeError): stamp=str(r[key])+' (original; timezone unconfirmed)'
                    events.append((instant,stamp,key,r['title'],r['temporal_confidence']))
        self.timeline.setPlainText('Discrete events only; no continuous coverage implied. Display zone: '+data['query']['zone']+'\n\n'+('\n'.join(' | '.join(e[1:]) for e in sorted(events)) if events else 'No known recording, upload or publication timestamps.'))
        q=data['query']; term=' '.join(filter(None,[q['location'],q.get('keywords',''),q['start'][:10]]))
        urls={'YouTube':'https://www.youtube.com/results?'+urlencode({'search_query':term}),'Wikimedia Commons':'https://commons.wikimedia.org/w/index.php?'+urlencode({'search':term,'title':'Special:MediaSearch','type':'image'}),'Google News':'https://news.google.com/search?'+urlencode({'q':term}),'Flickr':'https://www.flickr.com/search/?'+urlencode({'text':term}),'OpenStreetMap':'https://www.openstreetmap.org/?'+urlencode({'mlat':q['lat'],'mlon':q['lon']})+'#map=15/'+str(q['lat'])+'/'+str(q['lon'])}
        self.links.setHtml('<h2>Open public platform searches</h2><p>These links use your location label, event keywords and date. They are not API results, are not automatically archived, and do not confirm an event or exact recording time. Apply platform filters and inspect each original.</p>'+''.join('<p><a href="'+html.escape(url,quote=True)+'">'+html.escape(name)+'</a></p>' for name,url in urls.items()))
        self.scene.clear(); self.scene.setSceneRect(-540,-90,1080,180)
        self.scene.addRect(-180,-90,360,180,map_pen('#667788'))
        q=data['query']; marker=max(q['radius']/111320*.04,.00002)
        self.street.set_data(q,self.records)
        self.scene.addEllipse(q['lon']-marker,-q['lat']-marker,marker*2,marker*2,map_pen('red'))
        dx=q['radius']/111320; import math
        self.scene.addEllipse(q['lon']-dx/max(.001,math.cos(math.radians(q['lat']))),-q['lat']-dx,2*dx/max(.001,math.cos(math.radians(q['lat']))),2*dx,map_pen('red'))
        for r in self.records:
            if r['lat'] is not None and r['lon'] is not None:
                longitude=map_longitude(r['lon'],q['lon'])
                item=self.scene.addEllipse(longitude-marker,-r['lat']-marker,marker*2,marker*2,map_pen('blue')); item.setToolTip(r['title']); item.setData(0,r['id'])
            geometry=r['raw'].get('geometry') or {}
            polygons=geometry.get('coordinates',[]) if geometry.get('type')=='MultiPolygon' else [geometry.get('coordinates',[])] if geometry.get('type')=='Polygon' else []
            for box in r['raw'].get('boxes',[]):
                try:
                    south,west,north,east=map(float,box.split())
                    polygons.append([[[west,south],[east,south],[east,north],[west,north],[west,south]]])
                except (ValueError,AttributeError): continue
            for polygon in polygons:
                if not polygon:continue
                from PySide6.QtGui import QPolygonF
                from PySide6.QtCore import QPointF
                try: shape=QPolygonF([QPointF(map_longitude(p[0],q['lon']),-p[1]) for p in polygon[0]])
                except (ValueError,TypeError,IndexError):continue
                item=self.scene.addPolygon(shape,map_pen('#698f99')); item.setToolTip(r['title']); item.setData(0,r['id'])
        from PySide6.QtCore import QRectF
        extent=max(dx*3,.02); width=extent/max(.05,math.cos(math.radians(q['lat'])))
        self.map.fitInView(QRectF(q['lon']-width,-q['lat']-extent,width*2,extent*2),Qt.KeepAspectRatio)
    def filter_rows(self):
        needle=self.filter.text().casefold()
        for i,r in enumerate(self.records): self.table.setRowHidden(i,needle not in json.dumps(r).casefold())
        row=self.table.currentRow()
        if row>=0 and self.table.isRowHidden(row):
            self.table.clearSelection();self.table.setCurrentCell(-1,-1);self.show_details()
        self.preview_timer.start()
    def show_details(self):
        i=self.table.currentRow()
        if 0<=i<len(self.records):
            record=self.records[i];self.details.setPlainText(json.dumps(record,indent=2,ensure_ascii=False))
            credit=preview_credit(record);visible=credit.split('\nOriginale:')[0]
            if len(visible)>350:visible=visible[:350]+'… (attribuzione completa nei metadati)'
            self.gallery_credit.setText(html.escape(visible).replace('\n',' · ')+' · <a href="'+html.escape(record['url'],quote=True)+'">Apri originale</a>');self.gallery_credit.setToolTip(html.escape(credit).replace('\n','<br>'))
        else:
            self.details.setPlainText('Select a result in the gallery or click a map feature to inspect the original record.')
            self.gallery_credit.setText('Seleziona un risultato per attribuzione, licenza e fonte originale.')
    def open_record(self,row,col):
        if 0<=row<len(self.records) and not QDesktopServices.openUrl(QUrl(self.records[row]['url'])):
            self.error('The default browser could not open this URL. Copy it from Original metadata.')
    def restore_query(self,data):
        self.applying_fields=True
        try:
            for key,edit in self.inputs.items(): edit.setText(str(data['query'][key]))
            self.resolved_location=self.inputs['location'].text(); self.resolved_coords=self.coords()
            self.date_snapshot=(self.inputs['start'].text(),self.inputs['end'].text())
            self.radius.setValue(data['query']['radius']); self.mode.setCurrentText(data['query']['mode'])
            for name,check in self.source_checks.items(): check.setChecked(data['coverage'].get(name,{}).get('status','NOT_STARTED')!='NOT_STARTED')
            for name,check in self.media_checks.items(): check.setChecked(name in data['query']['media'])
            self.auto_zone.blockSignals(True); self.auto_zone.setChecked(False); self.auto_zone.blockSignals(False)
            self.inputs['zone'].setReadOnly(False)
            self.field_status.setText('Parametri originali ripristinati dall’archivio, compreso il fuso orario salvato.')
        finally:self.applying_fields=False
    def reopen(self):
        from PySide6.QtWidgets import QInputDialog
        choices=[f'{created} | {id}' for id,created in self.archive.list()]
        if not choices: self.statusBar().showMessage('No archived investigations. Start a search first.'); return
        choice,ok=QInputDialog.getItem(self,'Investigations','Select archive',choices,0,False)
        if ok:
            id=choice.split(' | ')[1]; self.restore_query(self.archive.load(id)); self.render(id)
    def export(self):
        if not self.current: return
        folder=QFileDialog.getExistingDirectory(self,'Export destination')
        if folder:
            try: export(self.archive.load(self.current),Path(folder)/self.current); self.statusBar().showMessage('Report exported')
            except Exception as e: self.error(str(e))
    def error(self,text):
        self.pending_search=False
        if not self.worker or not self.worker.isRunning(): self.start.setEnabled(True)
        QMessageBox.warning(self,'GeoTrace',text)
    def closeEvent(self,event):
        if hasattr(self,'geo') and self.geo.isRunning(): event.ignore(); return
        if self.worker and self.worker.isRunning():
            self.worker.cancel(); event.ignore(); self.statusBar().showMessage('Cancelling search; close again after completion'); return
        self.images.close();event.accept()

def main():
    app=QApplication(sys.argv); app.setStyle('Fusion'); app.setFont(QFont('Segoe UI',10))
    def fatal(kind,value,tb):
        import traceback
        folder=data_dir(); folder.mkdir(parents=True,exist_ok=True)
        log=folder/'error.log'
        with log.open('a',encoding='utf-8') as f: traceback.print_exception(kind,value,tb,file=f)
        QMessageBox.critical(None,'GeoTrace error',str(value)+'\n\nDetails: '+str(log))
    sys.excepthook=fatal
    try: window=Window(); window.show()
    except Exception:
        fatal(*sys.exc_info()); return 1
    sys.exit(app.exec())

if __name__=='__main__': main()
