"""Public API adapters; catalog discovery never implies permission to download."""
import asyncio
import dataclasses
import httpx
import json
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from .core import Record, distance

USER_AGENT = 'GeoTrace/0.2 (https://github.com/motthz/GeoTrace)'

class ProviderBusy(RuntimeError): pass

def time_confidence(value):
    try:
        if datetime.fromisoformat(value.replace('Z','+00:00')).tzinfo is not None:return 'METADATA_SUPPORTED'
    except (ValueError,TypeError,AttributeError):pass
    return 'UNKNOWN'

@dataclasses.dataclass(frozen=True)
class Capabilities:
    name: str
    endpoint: str
    media: tuple = ('satellite',)
    geography: str = 'bounding box intersection; not proof of recording at center'
    history: bool = True
    temporal_precision: str = 'provider acquisition metadata'
    auth: str = 'public catalog; asset authentication may differ'
    download: str = 'metadata only by default; inspect asset license'
    rate_limit: str = 'one active request, retries respect Retry-After'
    limitations: str = 'bounded catalog query; not exhaustive'
    api: bool = True

class Provider:
    def __init__(self, capabilities): self.cap = capabilities
    async def search(self, client, q, request): raise NotImplementedError

class Stac(Provider):
    async def search(self, client, q, request):
        records=[]
        for box in q.boxes():
            params={'bbox':','.join(map(str,box)),'datetime':q.start_utc.replace('+00:00','Z')+'/'+q.end_utc.replace('+00:00','Z'),'limit':{'QUICK':25,'DEEP':75,'EXTENDED':100}[q.mode]}
            if self.cap.name=='Copernicus': params['collections']='sentinel-2-l2a'
            data=await request(client,'GET',self.cap.endpoint+'/search',params=params)
            if not isinstance(data.get('features'),list): raise RuntimeError('Invalid STAC response: features array missing')
            for item in data.get('features',[]):
                p=item.get('properties',{})
                url=next((l['href'] for l in item.get('links',[]) if l['rel']=='self'), self.cap.endpoint+'/collections/'+str(item.get('collection',''))+'/items/'+item['id'])
                assets=item.get('assets',{})
                thumb=next((v['href'] for k,v in assets.items() if k in ('thumbnail','rendered_preview')),None)
                recording=p.get('datetime') or p.get('start_datetime')
                records.append(Record(self.cap.name,item['id'],url,p.get('title') or item['id'],'satellite',item,recording=recording,temporal_confidence=time_confidence(recording),geographic_confidence='APPROXIMATE_LOCATION',description='Catalog footprint intersects search bounding box; it may lie outside the radius. Acquisition interval in raw metadata.',license=p.get('license','See collection license'),thumbnail=thumb))
        return records

class Commons(Provider):
    async def search(self,client,q,request):
        data=await request(client,'GET',self.cap.endpoint,params=dict(action='query',format='json',generator='geosearch',ggscoord=f'{q.lat}|{q.lon}',ggsradius=min(q.radius,10000),ggsnamespace=6,ggslimit=50,prop='imageinfo|coordinates',iiprop='url|timestamp|extmetadata|mime',iiurlwidth=240))
        if 'error' in data:
            if data['error'].get('code') in ('cirrussearch-too-busy-error','maxlag','ratelimited'):
                raise ProviderBusy(data['error'].get('info','Provider is busy; try again later'))
            raise RuntimeError(str(data['error']))
        out=[]
        for p in data.get('query',{}).get('pages',{}).values():
            ii=p.get('imageinfo',[{}])[0]; meta=ii.get('extmetadata',{}); coords=p.get('coordinates',[{}])[0]
            lat,lon=coords.get('lat'),coords.get('lon')
            try:
                lat,lon=float(lat),float(lon)
                if not (-90<=lat<=90 and -180<=lon<=180):raise ValueError('Invalid coordinate')
            except (ValueError,TypeError):lat=lon=None
            if lat is not None and distance(q.lat,q.lon,lat,lon)>q.radius: continue
            # Commons DateTimeOriginal is free text; retain it raw, never silently interpret it.
            out.append(Record(self.cap.name,str(p['pageid']),ii.get('descriptionurl','https://commons.wikimedia.org/wiki/'+p['title'].replace(' ','_')),p['title'],'video' if ii.get('mime','').startswith('video/') or ii.get('url','').lower().endswith(('.webm','.ogv')) else 'image',p,lat=lat,lon=lon,geographic_confidence='EXACT_COORDINATES' if lat is not None else 'UNKNOWN',upload=ii.get('timestamp'),license=meta.get('LicenseShortName',{}).get('value','Unknown'),thumbnail=ii.get('thumburl'),description='Recording time unconfirmed. Nearby candidate, not confirmed within requested time interval.'))
        return out

class Nasa(Provider):
    async def search(self,client,q,request):
        out=[]
        for box in q.boxes():
            data=await request(client,'GET',self.cap.endpoint,params={'short_name':'HLSL30','bounding_box':','.join(map(str,box)),'temporal':q.start_utc.replace('+00:00','Z')+','+q.end_utc.replace('+00:00','Z'),'page_size':25})
            if not isinstance(data.get('feed'),dict): raise RuntimeError('Invalid NASA response: feed missing')
            for e in data.get('feed',{}).get('entry',[]):
                url='https://search.earthdata.nasa.gov/search/granules?p='+e.get('collection_concept_id','')
                url=next((l['href'] for l in e.get('links',[]) if l.get('rel','').endswith('/metadata#')),url)
                out.append(Record(self.cap.name,e['id'],url,e.get('title') or e['id'],'satellite',e,recording=e.get('time_start'),modified=e.get('updated'),temporal_confidence=time_confidence(e.get('time_start')),geographic_confidence='APPROXIMATE_LOCATION',description='Earthdata granule footprint intersects bounding box; raw metadata preserves acquisition end.'))
        return out

PROVIDERS=[
    Stac(Capabilities('Copernicus','https://stac.dataspace.copernicus.eu/v1',limitations='Sentinel-2 L2A only; bounded first page; bounding box may exceed radius')),
    Stac(Capabilities('Earth Search','https://earth-search.aws.element84.com/v1')),
    Nasa(Capabilities('NASA Earthdata','https://cmr.earthdata.nasa.gov/search/granules.json',limitations='HLSL30 only; first 25 granules; bounding box may exceed radius')),
    Commons(Capabilities('Wikimedia Commons','https://commons.wikimedia.org/w/api.php',media=('image','video'),geography='geotag radius limited to 10 km',temporal_precision='upload only; recording date unconfirmed',limitations='50 nearby candidates maximum; radius capped at 10 km; temporal relevance unconfirmed')),
]

RESTRICTED={
    'YouTube':('AUTH_REQUIRED','https://developers.google.com/youtube/v3','YouTube Data API key and quota required; not configured'),
    'Flickr':('AUTH_REQUIRED','https://www.flickr.com/services/api/','Flickr API key required; not configured'),
    'Reddit':('AUTH_REQUIRED','https://www.reddit.com/dev/api/','Authorized API access required; not configured'),
    'Vimeo':('AUTH_REQUIRED','https://developer.vimeo.com/','Access token and permitted search scope required'),
    'Dailymotion':('UNSUPPORTED','https://developers.dailymotion.com/','Connector not implemented'),
    'Instagram / Facebook / TikTok':('AUTH_REQUIRED','https://developers.facebook.com/','Platform approval and permitted research/search scope required; no generic public search connector'),
    'News / RSS':('UNSUPPORTED','https://www.rssboard.org/rss-specification','No permitted local feed configured; connector not implemented'),
    'Historical webcams':('UNSUPPORTED','https://www.skylinewebcams.com/','No authorized historical recording interface configured'),
    'Commercial imagery':('AUTH_REQUIRED','https://www.planet.com/','Licensed catalog account required; paid services disabled'),
}

async def request(client, method, url, **kwargs):
    for attempt in range(3):
        response=await client.request(method,url,**kwargs)
        if response.status_code not in (429,500,502,503,504):
            response.raise_for_status(); return response.json()
        if attempt==2: response.raise_for_status()
        retry=response.headers.get('Retry-After','')
        try: delay=float(retry)
        except ValueError:
            try: delay=max(0,(parsedate_to_datetime(retry)-datetime.now(timezone.utc)).total_seconds())
            except (ValueError,TypeError): delay=2**attempt
        # Do not retry earlier than a long provider-mandated delay.
        if delay>30: response.raise_for_status()
        await asyncio.sleep(max(delay,2**attempt))

async def search(archive,q,callback=lambda *args:None, selected=None, investigation=None):
    if selected is not None:
        selected=[name.strip() for name in selected]
        if not selected or set(selected)-{p.cap.name for p in PROVIDERS}: raise ValueError('Invalid or empty provider selection')
    if investigation and archive.load(investigation)['query']!=json.loads(json.dumps(dataclasses.asdict(q))):
        raise ValueError('Resume parameters differ from the archived investigation')
    id=investigation or archive.create(q)
    for name,(status,url,reason) in RESTRICTED.items():
        archive.status(id,name,status=status,reason=reason,official_url=url,access='LIMITED')
    async with httpx.AsyncClient(headers={'User-Agent':USER_AGENT},timeout=35,follow_redirects=True) as client:
        async def run(provider):
            cap=dataclasses.asdict(provider.cap); name=provider.cap.name
            if selected is not None and name not in selected or not set(q.media).intersection(provider.cap.media):
                archive.status(id,name,status='NOT_STARTED',reason='Not selected',capabilities=cap); return
            archive.status(id,name,status='RUNNING',capabilities=cap); callback(name,'RUNNING',0)
            try:
                async with asyncio.timeout(120): records=await provider.search(client,q,request)
                records=[r for r in records if r.media in q.media]
                for r in records: archive.save(id,r)
                status='SUCCESS' if records else 'NO_RESULTS'
                archive.status(id,name,status=status,count=len(records),partial=True,reason=provider.cap.limitations,capabilities=cap)
                callback(name,status,len(records))
            except asyncio.CancelledError:
                archive.status(id,name,status='ERROR',reason='Cancelled; saved records retained',capabilities=cap); raise
            except Exception as exc:
                code=exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None
                status='RATE_LIMITED' if code==429 or isinstance(exc,ProviderBusy) else 'AUTH_REQUIRED' if code==401 else 'UNAVAILABLE' if code==403 or isinstance(exc,httpx.TransportError) else 'ERROR'
                archive.status(id,name,status=status,reason=str(exc),capabilities=cap); callback(name,status,0)
        await asyncio.gather(*(run(p) for p in PROVIDERS))
    return id

async def geocode(text, reverse=False):
    # Sequential callers must leave at least one second between requests.
    async with httpx.AsyncClient(headers={'User-Agent':USER_AGENT},timeout=20) as c:
        if reverse:
            lat,lon=text.split(',')
            return await request(c,'GET','https://nominatim.openstreetmap.org/reverse',params={'lat':lat,'lon':lon,'format':'jsonv2','namedetails':1})
        return await request(c,'GET','https://nominatim.openstreetmap.org/search',params={'q':text,'format':'jsonv2','limit':5,'namedetails':1})
