"""Bounded asynchronous public image loading, shared by previews and map tiles."""
from collections import OrderedDict,deque
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit,unquote
from html.parser import HTMLParser
from PySide6.QtCore import QObject,Signal,QUrl,QBuffer,QByteArray,QIODevice,QSize,Qt
from PySide6.QtGui import QImage,QImageReader
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkReply,QNetworkProxy,QNetworkProxyFactory
from .core import data_dir
from .providers import USER_AGENT

PREVIEW_HOSTS=('wikimedia.org','creodias.eu','copernicus.eu','amazonaws.com','nasa.gov','usgs.gov','element84.com')
MAX_BYTES=3*1024*1024

def preview_credit(record):
    class Plain(HTMLParser):
        def __init__(self):super().__init__();self.text=[]
        def handle_data(self,data):self.text.append(data)
    parser=Plain()
    try:artist=record['raw']['imageinfo'][0]['extmetadata']['Artist']['value']
    except (KeyError,IndexError,TypeError):artist='Autore non indicato nei metadati'
    parser.feed(str(artist));author=' '.join(' '.join(parser.text).split())
    return f"Fonte: {record['provider']}\nAutore: {author}\nLicenza: {record.get('license') or 'Non indicata'}\nOriginale: {record['url']}"

def image_url_allowed(url,kind='preview'):
    try:
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):return False
        host=p.hostname.lower()
        if kind=='tile':return host=='tile.openstreetmap.org'
        return any(host==suffix or host.endswith('.'+suffix) for suffix in PREVIEW_HOSTS)
    except (ValueError,TypeError,AttributeError):return False

def image_expiry(headers,kind,clock=None):
    clock=time.time() if clock is None else clock
    control=headers.get('cache-control','').lower()
    if 'no-store' in control or 'no-cache' in control:return None
    for part in control.split(','):
        key,_,value=part.strip().partition('=')
        if key=='max-age':
            try:return clock+max(0,int(value.strip('"'))-int(headers.get('age','0')))
            except ValueError:pass
    if headers.get('expires'):
        try:return parsedate_to_datetime(headers['expires']).timestamp()
        except (TypeError,ValueError):pass
    return clock+(7*86400 if kind=='tile' else 86400)

def decode_image(data,kind):
    if len(data)>MAX_BYTES:raise ValueError('Image exceeds the byte limit')
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.ReadOnly)
    reader=QImageReader(buffer);size=reader.size()
    if bytes(reader.format()).lower() not in (b'jpeg',b'jpg',b'png',b'gif',b'webp',b'bmp'):raise ValueError('Unsupported image format')
    if not size.isValid() or size.width()>4096 or size.height()>4096:raise ValueError('Unsupported or oversized image')
    if kind=='tile' and (size.width()!=256 or size.height()!=256):raise ValueError('Unexpected map tile size')
    if kind!='tile':reader.setScaledSize(size.scaled(QSize(240,180),Qt.KeepAspectRatio))
    reader.setAutoTransform(True);image=reader.read()
    if image.isNull():raise ValueError('Image cannot be decoded')
    return image

class ImageCache:
    def __init__(self,folder=None,max_bytes=128*1024*1024):
        self.folder=Path(folder or data_dir()/'image-cache');self.max_bytes=max_bytes;self.disabled=False
        try:self.folder.mkdir(parents=True,exist_ok=True)
        except OSError:self.disabled=True
    def paths(self,url):
        key=hashlib.sha256(url.encode('utf-8')).hexdigest()
        return self.folder/(key+'.bin'),self.folder/(key+'.json')
    def read(self,url):
        if self.disabled:return None
        body,meta=self.paths(url)
        try:
            info=json.loads(meta.read_text(encoding='utf-8'))
            if info['expires']<=time.time() or body.stat().st_size>MAX_BYTES:return None
            data=body.read_bytes()
            if hashlib.sha256(data).hexdigest()!=info['sha256']:return None
            return data
        except (OSError,ValueError,KeyError,TypeError):return None
    def write(self,url,data,expires):
        if self.disabled or expires is None or expires<=time.time():return
        body,meta=self.paths(url);temporary=body.with_suffix('.tmp')
        temporary.write_bytes(data);temporary.replace(body)
        meta.write_text(json.dumps({'expires':expires,'sha256':hashlib.sha256(data).hexdigest()}),encoding='utf-8')
        files=sorted(self.folder.glob('*.bin'),key=lambda p:p.stat().st_mtime)
        total=sum(p.stat().st_size for p in files)
        for path in files:
            if total<=self.max_bytes:break
            total-=path.stat().st_size;path.unlink(missing_ok=True);path.with_suffix('.json').unlink(missing_ok=True)

class ImageBroker(QObject):
    ready=Signal(str,QImage,str)
    def __init__(self,parent=None,cache=None):
        super().__init__(parent);self.cache=cache or ImageCache();self.manager=QNetworkAccessManager(self)
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        proxy=os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
        if proxy:
            p=urlsplit(proxy)
            if p.scheme in ('http','socks5') and p.hostname:
                type_=QNetworkProxy.Socks5Proxy if p.scheme=='socks5' else QNetworkProxy.HttpProxy
                self.manager.setProxy(QNetworkProxy(type_,p.hostname,p.port or 8080,unquote(p.username or ''),unquote(p.password or '')))
        self.queue=deque();self.jobs={};self.active={};self.memory=OrderedDict();self.errors={};self.closing=False
    def result(self,url,kind='preview'):
        if not image_url_allowed(url,kind):return QImage(),'Anteprima non disponibile tramite HTTPS da una fonte supportata'
        if url in self.memory:
            self.memory.move_to_end(url);return self.memory[url],''
        return QImage(),self.errors.get(url,'')
    def request(self,url,kind='preview'):
        if not isinstance(url,str):return
        if self.closing or url in self.jobs or url in self.memory or url in self.errors:return
        if not image_url_allowed(url,kind):return
        cached=self.cache.read(url)
        if cached:
            try:self._remember(url,decode_image(cached,kind));return
            except ValueError:pass
        if len(self.queue)>=128:return
        self.jobs[url]=kind;self.queue.append(url);self._pump()
    def keep_pending(self,kind,urls):
        urls=set(urls);kept=deque()
        for url in self.queue:
            if self.jobs.get(url)==kind and url not in urls:self.jobs.pop(url,None)
            else:kept.append(url)
        self.queue=kept
    def retry_errors(self):self.errors.clear()
    def _remember(self,url,image):
        self.memory[url]=image;self.memory.move_to_end(url)
        while len(self.memory)>256:self.memory.popitem(last=False)
    def _pump(self):
        while not self.closing and self.queue and len(self.active)<4:
            selected=None
            for _ in range(len(self.queue)):
                url=self.queue.popleft();kind=self.jobs.get(url)
                if sum(self.jobs.get(job['url'])==kind for job in self.active.values())<2:selected=url;break
                self.queue.append(url)
            if selected is None:break
            self._send(selected,selected,0)
    def _send(self,url,target,hops):
        request=QNetworkRequest(QUrl(target));request.setRawHeader(b'User-Agent',USER_AGENT.encode('ascii'))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute,QNetworkRequest.ManualRedirectPolicy);request.setTransferTimeout(15000)
        reply=self.manager.get(request);reply.setReadBufferSize(MAX_BYTES+1);self.active[reply]={'url':url,'data':bytearray(),'oversize':False,'redirects':hops}
        reply.readyRead.connect(lambda reply=reply:self._read(reply));reply.finished.connect(lambda reply=reply:self._finished(reply))
    def _read(self,reply):
        job=self.active.get(reply)
        if not job or job['oversize']:return
        job['data'].extend(bytes(reply.readAll()))
        if len(job['data'])>MAX_BYTES:job['oversize']=True;reply.abort()
    def _finished(self,reply):
        self._read(reply);job=self.active.pop(reply,None)
        if job is None:return
        url=job['url'];kind=self.jobs.get(url,'preview');error='';image=QImage()
        code=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if code in (301,302,303,307,308) and not self.closing:
            target=reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
            resolved=reply.url().resolved(target).toString() if isinstance(target,QUrl) else ''
            if job['redirects']<3 and image_url_allowed(resolved,kind):
                reply.deleteLater();self._send(url,resolved,job['redirects']+1);return
        self.jobs.pop(url,None)
        try:
            if job['oversize']:raise ValueError('Anteprima troppo grande')
            if reply.error()!=QNetworkReply.NoError or code!=200:raise ValueError('Caricamento non riuscito: '+('HTTP '+str(code) if code else reply.errorString()))
            image=decode_image(bytes(job['data']),kind)
            headers={bytes(k).decode('latin1').lower():bytes(v).decode('latin1') for k,v in reply.rawHeaderPairs()}
            try:self.cache.write(url,bytes(job['data']),image_expiry(headers,kind))
            except OSError:pass  # Display may succeed even if the optional cache is full/read-only.
            self._remember(url,image)
        except (ValueError,TypeError) as exc:error=str(exc);self.errors[url]=error
        reply.deleteLater()
        if not self.closing:self.ready.emit(url,image,error)
        self._pump()
    def close(self):
        self.closing=True;self.queue.clear()
        for reply in list(self.active):reply.abort()
