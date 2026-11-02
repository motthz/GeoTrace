from __future__ import annotations
import dataclasses
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

def now():
    return datetime.now(timezone.utc).isoformat()

def utc(value: str, zone: str):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        tz = ZoneInfo(zone)
        a, b = dt.replace(tzinfo=tz, fold=0), dt.replace(tzinfo=tz, fold=1)
        if a.utcoffset() != b.utcoffset():
            raise ValueError('Ambiguous or nonexistent local time: supply an explicit UTC offset')
        dt = a
    return dt.astimezone(timezone.utc).isoformat()

def canonical(url):
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('Expected a public HTTP(S) source URL')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ''))

@dataclasses.dataclass
class Query:
    lat: float = 46.24645
    lon: float = 9.42375
    radius: int = 1000
    start: str = '2026-10-31T01:00:00'
    end: str = '2026-10-31T02:00:00'
    zone: str = 'Europe/Rome'
    location: str = 'Samolaco railway station, Italy'
    keywords: str = ''
    mode: str = 'QUICK'
    media: tuple = ('image', 'video', 'satellite', 'article')

    def __post_init__(self):
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180 and 50 <= self.radius <= 100000):
            raise ValueError('Invalid coordinates or radius (50–100000 m)')
        if self.mode not in ('QUICK', 'DEEP', 'EXTENDED'):
            raise ValueError('Invalid search mode')
        if self.start_utc > self.end_utc:
            raise ValueError('Start must precede end')

    @property
    def start_utc(self): return utc(self.start, self.zone)
    @property
    def end_utc(self): return utc(self.end, self.zone)
    def boxes(self):
        dy = math.degrees(self.radius / 6371008.8)
        south, north = max(-90, self.lat-dy), min(90, self.lat+dy)
        if abs(self.lat)+dy >= 90:
            return [[-180, south, 180, north]]
        dx = math.degrees(math.asin(min(1, math.sin(math.radians(dy))/math.cos(math.radians(self.lat)))))
        west, east = self.lon-dx, self.lon+dx
        if west < -180: return [[west+360,south,180,north],[-180,south,east,north]]
        if east > 180: return [[west,south,180,north],[-180,south,east-360,north]]
        return [[west,south,east,north]]

def distance(lat1, lon1, lat2, lon2):
    a,b,c,d=map(math.radians,(lat1,lon1,lat2,lon2))
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 12742017.6*math.asin(min(1, math.sqrt(h)))

@dataclasses.dataclass
class Record:
    provider: str
    provider_id: str
    url: str
    title: str
    media: str
    raw: dict
    description: str = ''
    lat: float | None = None
    lon: float | None = None
    geographic_confidence: str = 'UNKNOWN'
    recording: str | None = None
    publication: str | None = None
    upload: str | None = None
    modified: str | None = None
    inferred: str | None = None
    temporal_confidence: str = 'UNKNOWN'
    license: str = 'Unknown; inspect original source'
    download_allowed: bool = False
    download_url: str | None = None
    thumbnail: str | None = None
    local_path: str | None = None
    sha256: str | None = None
    verification: str = 'UNREVIEWED'
    discovered: str = dataclasses.field(default_factory=now)
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self): self.url = canonical(self.url)

class Archive:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY, query TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS records(investigation TEXT, id TEXT, provider TEXT, provider_id TEXT, url TEXT, payload TEXT, PRIMARY KEY(investigation,provider,provider_id));
            CREATE TABLE IF NOT EXISTS coverage(investigation TEXT, provider TEXT, payload TEXT, PRIMARY KEY(investigation,provider));
            PRAGMA user_version=1;''')
    def connect(self): return sqlite3.connect(self.path, timeout=30)
    def create(self, q):
        id = str(uuid.uuid4())
        with self.connect() as c: c.execute('INSERT INTO investigations VALUES(?,?,?)',(id,json.dumps(dataclasses.asdict(q)),now()))
        return id
    def save(self, id, record):
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?)',(id,record.id,record.provider,record.provider_id,record.url,json.dumps(dataclasses.asdict(record))))
    def status(self,id,provider,**data):
        with self.connect() as c: c.execute('INSERT OR REPLACE INTO coverage VALUES(?,?,?)',(id,provider,json.dumps(data)))
    def load(self,id):
        with self.connect() as c:
            row=c.execute('SELECT query,created FROM investigations WHERE id=?',(id,)).fetchone()
            if not row: raise KeyError(id)
            return dict(id=id,query=json.loads(row[0]),created=row[1],records=[json.loads(r[0]) for r in c.execute('SELECT payload FROM records WHERE investigation=?',(id,))],coverage={r[0]:json.loads(r[1]) for r in c.execute('SELECT provider,payload FROM coverage WHERE investigation=?',(id,))})
    def list(self):
        with self.connect() as c: return c.execute('SELECT id,created FROM investigations ORDER BY created DESC').fetchall()

def duplicate_groups(records):
    groups={}
    for r in records:
        key=r.get('sha256') or canonical(r['url'])
        groups.setdefault(key,[]).append(r['id'])
    return [v for v in groups.values() if len(v)>1]

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
