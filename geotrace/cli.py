import argparse
import asyncio
import dataclasses
import json
import sqlite3
from pathlib import Path
from .core import Archive,Query
from .providers import search
from .reports import export

def main():
    parser=argparse.ArgumentParser(description='GeoTrace public metadata discovery')
    inputs=parser.add_mutually_exclusive_group()
    inputs.add_argument('--query',type=Path,help='JSON Query fields; defaults to Samolaco investigation')
    from .core import data_dir
    parser.add_argument('--archive',default=str(data_dir()/'archive.sqlite'))
    parser.add_argument('--export',type=Path)
    parser.add_argument('--sources',help='Comma-separated connector names')
    inputs.add_argument('--resume',help='Repeat bounded queries and merge into an existing investigation')
    args=parser.parse_args()
    try:
        archive=Archive(args.archive)
        q=Query(**(archive.load(args.resume)['query'] if args.resume else json.loads(args.query.read_text(encoding='utf-8')) if args.query else {}))
        id=asyncio.run(search(archive,q,lambda *x:print(*x,flush=True),args.sources.split(',') if args.sources is not None else None,args.resume))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc: parser.error(str(exc))
    except KeyboardInterrupt: parser.exit(130,'Search cancelled; provider checkpoints and previous records remain in the archive.\n')
    data=archive.load(id); print(json.dumps({'id':id,'records':len(data['records']),'coverage':data['coverage']},indent=2))
    if args.export: export(data,args.export/id)

if __name__=='__main__': main()
