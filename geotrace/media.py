"""Optional local processing. No model or footage is downloaded automatically."""
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .core import canonical,sha256

def public_url(url):
    canonical(url); host=urlsplit(url).hostname
    for info in socket.getaddrinfo(host,None):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError('Download target must be a public address')

def download(record,folder,max_bytes=100*1024*1024):
    if not record.download_allowed or not record.download_url:
        raise PermissionError('Explicit provider download permission and asset URL required')
    public_url(record.download_url)
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    target=folder/(record.id+'.media'); part=target.with_suffix('.part')
    try:
        with httpx.stream('GET',record.download_url,follow_redirects=False,timeout=30) as response:
            response.raise_for_status()
            if response.is_redirect: raise PermissionError('Redirect requires separate target validation')
            size=0
            with part.open('wb') as f:
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>max_bytes: raise ValueError('Download size limit exceeded')
                    f.write(chunk)
        part.replace(target); record.local_path=str(target); record.sha256=sha256(target)
        return target
    except BaseException:
        part.unlink(missing_ok=True); raise

def perceptual_hash(path):
    from PIL import Image
    import imagehash
    with Image.open(path) as image: return str(imagehash.phash(image))
