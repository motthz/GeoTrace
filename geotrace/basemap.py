"""Native Qt slippy map. Public OSM tiles are current context, not historical evidence."""
import math
from PySide6.QtCore import Qt,Signal,QTimer,QPointF,QRectF
from PySide6.QtGui import QColor,QPen,QBrush,QPixmap,QPolygonF
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QGraphicsView,QGraphicsScene,QGraphicsItem

MERCATOR_LIMIT=85.0511287798066

def project(latitude,longitude,center_longitude=0):
    if not -MERCATOR_LIMIT<=latitude<=MERCATOR_LIMIT:raise ValueError('Latitude outside Web Mercator coverage')
    longitude=center_longitude+(longitude-center_longitude+180)%360-180
    return QPointF((longitude+180)/360*256,(1-math.asinh(math.tan(math.radians(latitude)))/math.pi)/2*256)

def circle(latitude,longitude,radius):
    lat=math.radians(latitude);lon=math.radians(longitude);delta=radius/6371008.8;points=[]
    for step in range(73):
        bearing=step*2*math.pi/72
        phi=math.asin(math.sin(lat)*math.cos(delta)+math.cos(lat)*math.sin(delta)*math.cos(bearing))
        lam=lon+math.atan2(math.sin(bearing)*math.sin(delta)*math.cos(lat),math.cos(delta)-math.sin(lat)*math.sin(phi))
        points.append((math.degrees(phi),math.degrees(lam)))
    return points

def pen(color):
    value=QPen(QColor(color));value.setCosmetic(True);value.setWidth(2);return value

class TileView(QGraphicsView):
    recordClicked=Signal(str)
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.setScene(QGraphicsScene(self));self.scene().setSceneRect(-512,0,1280,256)
        self.setDragMode(QGraphicsView.ScrollHandDrag);self.setBackgroundBrush(QColor('#e7edef'));self.zoom=12
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.horizontalScrollBar().valueChanged.connect(self.changed);self.verticalScrollBar().valueChanged.connect(self.changed)
        self.set_zoom(12)
    def set_zoom(self,zoom):
        zoom=max(2,min(19,zoom));center=self.mapToScene(self.viewport().rect().center())
        self.zoom=zoom;self.resetTransform();self.scale(2**zoom,2**zoom);self.centerOn(center);self.changed.emit()
    def wheelEvent(self,event):
        before=self.mapToScene(event.position().toPoint());self.set_zoom(self.zoom+(1 if event.angleDelta().y()>0 else -1))
        after=self.mapToScene(event.position().toPoint());self.centerOn(self.mapToScene(self.viewport().rect().center())+before-after)
        self.changed.emit();event.accept()
    def resizeEvent(self,event):super().resizeEvent(event);self.changed.emit()
    def mousePressEvent(self,event):self.pressed=event.position().toPoint();super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        moved=(event.position().toPoint()-getattr(self,'pressed',event.position().toPoint())).manhattanLength()>5
        if not moved:
            for item in self.items(event.position().toPoint()):
                if item.data(0):self.recordClicked.emit(item.data(0));break
        super().mouseReleaseEvent(event);self.changed.emit()

class BasemapPanel(QWidget):
    recordClicked=Signal(str)
    def __init__(self,broker,parent=None):
        super().__init__(parent);self.broker=broker;self.query=None;self.record_key=None;self.query_key=None;self.overlay=[];self.tiles={};self.needed={};self.valid=False;self.center_pending=False
        layout=QVBoxLayout(self);bar=QHBoxLayout();layout.addLayout(bar)
        self.status=QLabel('Apri una ricerca per visualizzare la cartografia.');self.status.setWordWrap(True);bar.addWidget(self.status,1)
        for text,action in [('+',lambda:self.view.set_zoom(self.view.zoom+1)),('−',lambda:self.view.set_zoom(self.view.zoom-1)),('Centra',self.center),('Riprova',self.retry)]:
            button=QPushButton(text);button.clicked.connect(action);bar.addWidget(button)
        self.view=TileView(self);layout.addWidget(self.view,1);self.view.recordClicked.connect(self.recordClicked)
        note=QLabel('Cartografia attuale, non una ripresa storica. Rosso: area di ricerca; blu: coordinate della fonte; grigio: impronte satellitari. <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>')
        note.setWordWrap(True);note.setOpenExternalLinks(True);layout.addWidget(note)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(120);self.timer.timeout.connect(self.update_tiles)
        self.view.changed.connect(lambda:self.timer.start());self.broker.ready.connect(self.image_ready)
    def set_data(self,query,records):
        key=(query['lat'],query['lon'],query['radius']);record_key=tuple(r['id'] for r in records)
        if key==self.query_key and record_key==self.record_key:return
        changed=key!=self.query_key;self.query=query;self.query_key=key;self.record_key=record_key
        self.valid=abs(query['lat'])+query['radius']/111195<MERCATOR_LIMIT
        for item in self.overlay:self.view.scene().removeItem(item)
        self.overlay=[]
        if not self.valid:
            for item in self.tiles.values():self.view.scene().removeItem(item)
            self.tiles={};self.needed={};self.broker.keep_pending('tile',[])
            self.status.setText('Area polare fuori dalla copertura Mercatore: usa la scheda delle coordinate offline.');return
        def polygon(points,color,id=None):
            try:shape=QPolygonF([project(lat,lon,query['lon']) for lat,lon in points])
            except (TypeError,ValueError):return
            item=self.view.scene().addPolygon(shape,pen(color));item.setZValue(2);item.setData(0,id);self.overlay.append(item)
            return item
        polygon(circle(query['lat'],query['lon'],query['radius']),'#cf3f3f')
        for r in records:
            geometry=r['raw'].get('geometry') or {}
            polygons=geometry.get('coordinates',[]) if geometry.get('type')=='MultiPolygon' else [geometry.get('coordinates',[])] if geometry.get('type')=='Polygon' else []
            for box in r['raw'].get('boxes',[]):
                try:
                    south,west,north,east=map(float,box.split());polygons.append([[[west,south],[east,south],[east,north],[west,north],[west,south]]])
                except (ValueError,AttributeError):pass
            for shape in polygons:
                if shape:
                    try:item=polygon([(p[1],p[0]) for p in shape[0]],'#667e88',r['id'])
                    except (TypeError,IndexError):continue
                    if item:item.setToolTip(r['title'])
            if r['lat'] is not None and r['lon'] is not None:
                try:point=project(r['lat'],r['lon'],query['lon'])
                except (TypeError,ValueError):continue
                # A fixed logical radius is sized for the current search; source point stays exact.
                item=self.view.scene().addEllipse(-5,-5,10,10,pen('#1167ad'),QBrush(QColor('#65a5d8')))
                item.setPos(point);item.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                item.setData(0,r['id']);item.setToolTip(r['title']);item.setZValue(3);self.overlay.append(item)
        center=project(query['lat'],query['lon'],query['lon'])
        item=self.view.scene().addEllipse(-3,-3,6,6,pen('#cf3f3f'));item.setPos(center);item.setFlag(QGraphicsItem.ItemIgnoresTransformations);item.setZValue(4);self.overlay.append(item)
        if changed:
            self.center_pending=True
            if self.isVisible():self.center()
        self.timer.start()
    def center(self):
        if not self.query or not self.valid:return
        q=self.query;meters_per_pixel=40075017*math.cos(math.radians(q['lat']))/256
        available=max(240,min(self.view.viewport().width(),self.view.viewport().height()))
        zoom=math.floor(math.log2(meters_per_pixel*available/(q['radius']*3)))
        self.view.set_zoom(zoom);self.view.centerOn(project(q['lat'],q['lon'],q['lon']));self.timer.start()
        self.center_pending=False
    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0,self.center if self.center_pending else self.update_tiles)
    def hideEvent(self,event):
        self.broker.keep_pending('tile',[]);super().hideEvent(event)
    def retry(self):self.broker.retry_errors();self.timer.start()
    def update_tiles(self):
        if not self.isVisible() or not self.query or not self.valid:return
        z=self.view.zoom;n=2**z;unit=256/n;rect=self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        needed={}
        for x in range(math.floor(rect.left()/unit),math.floor(rect.right()/unit)+1):
            for y in range(max(0,math.floor(rect.top()/unit)),min(n-1,math.floor(rect.bottom()/unit))+1):
                needed[(z,x,y)]=f'https://tile.openstreetmap.org/{z}/{x%n}/{y}.png'
        # Only the visible viewport: no prefetch, no area downloads.
        self.needed=needed;self.broker.keep_pending('tile',needed.values())
        for key in list(self.tiles):
            if key not in needed:self.view.scene().removeItem(self.tiles.pop(key))
        for key,url in needed.items():
            if key in self.tiles:continue
            self.broker.request(url,'tile');image,error=self.broker.result(url,'tile')
            if not image.isNull():self.put_tile(key,image)
        self.update_status()
    def put_tile(self,key,image):
        if key in self.tiles or key not in self.needed:return
        z,x,y=key;item=self.view.scene().addPixmap(QPixmap.fromImage(image));item.setScale(1/2**z);item.setPos(x*256/2**z,y*256/2**z);item.setZValue(-10);self.tiles[key]=item
    def image_ready(self,url,image,error):
        for key,expected in self.needed.items():
            if url==expected and not image.isNull():self.put_tile(key,image)
        if self.valid:self.update_status()
        if url in self.needed.values() and not error:self.timer.start()
    def update_status(self):
        errors=sum(bool(self.broker.result(url,'tile')[1]) for url in self.needed.values())
        self.status.setText(f'Zoom {self.view.zoom} · {len(self.tiles)}/{len(self.needed)} riquadri visibili caricati'+(f' · {errors} non disponibili; puoi usare la mappa offline' if errors else ''))
