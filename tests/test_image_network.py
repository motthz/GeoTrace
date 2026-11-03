"""Mock Qt replies, never real network or real investigation results."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QObject,QTimer,QEventLoop,QIODevice,QUrl
from PySide6.QtNetwork import QNetworkReply,QNetworkRequest
from PySide6.QtWidgets import QApplication
from geotrace.images import ImageBroker,ImageCache,MAX_BYTES
from test_visual import png

class Reply(QNetworkReply):
    def __init__(self,request,status,body,redirect=None):
        super().__init__();self.body=body;self.offset=0;self.setUrl(request.url());self.setRequest(request)
        self.setAttribute(QNetworkRequest.HttpStatusCodeAttribute,status)
        self.setRawHeader(b'Cache-Control',b'public,max-age=600')
        if redirect:self.setAttribute(QNetworkRequest.RedirectionTargetAttribute,QUrl(redirect))
        self.open(QIODevice.ReadOnly);QTimer.singleShot(0,self.deliver)
    def bytesAvailable(self):return len(self.body)-self.offset+super().bytesAvailable()
    def readData(self,max_size):
        chunk=self.body[self.offset:self.offset+max_size];self.offset+=len(chunk);return chunk
    def abort(self):
        if not self.isFinished():self.setError(QNetworkReply.OperationCanceledError,'Fixture cancelled');self.setFinished(True);self.finished.emit()
    def deliver(self):
        if self.isFinished():return
        self.readyRead.emit()
        if not self.isFinished():self.setFinished(True);self.finished.emit()

class Manager(QObject):
    def __init__(self,responses):super().__init__();self.responses=responses;self.requests=[];self.replies=[]
    def get(self,request):
        self.requests.append(request.url().toString());reply=Reply(request,*self.responses[request.url().toString()]);self.replies.append(reply);return reply

def broker_for(tmp_path,responses):
    app=QApplication.instance() or QApplication([]);broker=ImageBroker(cache=ImageCache(tmp_path));broker.manager=Manager(responses);return app,broker

def complete(broker):
    loop=QEventLoop();timer=QTimer();timer.setInterval(10)
    timer.timeout.connect(lambda:loop.quit() if not broker.jobs else None);timer.start();QTimer.singleShot(2000,loop.quit);loop.exec();timer.stop();assert not broker.jobs

def test_trusted_redirect_and_request_deduplication(tmp_path):
    a='https://thumb.wikimedia.org/first';b='https://upload.wikimedia.org/image.png'
    app,broker=broker_for(tmp_path,{a:(302,b'',b),b:(200,png())});broker.request(a);broker.request(a);complete(broker)
    assert broker.manager.requests==[a,b]
    assert not broker.result(a)[0].isNull() and broker.cache.read(a)
    broker.close()

def test_redirect_to_untrusted_host_is_never_requested(tmp_path):
    a='https://thumb.wikimedia.org/first'
    app,broker=broker_for(tmp_path,{a:(302,b'','https://localhost/private')});broker.request(a);complete(broker)
    assert broker.manager.requests==[a] and broker.result(a)[1]
    assert broker.cache.read(a) is None;broker.close()

def test_http_failure_and_oversize_are_explicit(tmp_path):
    a='https://thumb.wikimedia.org/missing';b='https://thumb.wikimedia.org/oversize'
    app,broker=broker_for(tmp_path,{a:(404,png()),b:(200,b'x'*(MAX_BYTES+1))});broker.request(a);broker.request(b);complete(broker)
    assert '404' in broker.result(a)[1] and broker.result(b)[1]
    assert broker.cache.read(a) is None and broker.cache.read(b) is None;broker.close()

def test_disk_failure_does_not_hide_successful_preview(tmp_path,monkeypatch):
    a='https://thumb.wikimedia.org/image.png';app,broker=broker_for(tmp_path,{a:(200,png())})
    def full(*args):raise OSError('Fixture disk full')
    monkeypatch.setattr(broker.cache,'write',full);broker.request(a);complete(broker)
    assert not broker.result(a)[0].isNull() and not broker.result(a)[1];broker.close()

def test_queue_is_bounded_per_role_and_close_aborts(tmp_path):
    urls=['https://thumb.wikimedia.org/'+str(i) for i in range(5)]
    app,broker=broker_for(tmp_path,{url:(200,png()) for url in urls})
    for url in urls:broker.request(url)
    assert len(broker.active)==2 and len(broker.queue)==3
    broker.close();assert not broker.active and not broker.queue
