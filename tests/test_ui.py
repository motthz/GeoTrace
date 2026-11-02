import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from geotrace.app import Window
from geotrace.core import Archive,Query

def test_ui_archive(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(); id=w.archive.create(Query()); w.render(id)
    assert w.table.rowCount()==0
    assert w.tabs.count()==5
    w.close()
