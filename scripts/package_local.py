#!/usr/bin/env python3
"""Package an explicitly selected local release; verify every archived member hash."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile
from package_release import source_files


def package(root,output,source_only=False):
    root=root.resolve();output=output.absolute()
    if output.exists() or root in output.parents:raise ValueError('Use a new ZIP outside the source tree')
    paths={str(p.relative_to(root)):p for p in source_files(root) if p.name!='MANIFEST.sha256'}
    if not source_only:
        for folder in ['models/trained','reports']:
            for p in (root/folder).rglob('*'):
                if p.is_symlink():raise ValueError('Symlink artifact refused')
                if p.is_file() and p.suffix in {'.json','.pt'}:paths[str(p.relative_to(root))]=p
        if 'models/trained/url-model.json' not in paths:raise ValueError('URL model missing')
        vision=paths.get('models/trained/vision-model.pt')
        if vision:
            import json
            report=json.loads(vision.with_suffix('.json').read_text())
            if hashlib.sha256(vision.read_bytes()).hexdigest()!=report['weights_sha256']:raise ValueError('CNN weight hash mismatch')
    manifest={}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,p in sorted(paths.items()):
            data=p.read_bytes();manifest[name]=hashlib.sha256(data).hexdigest();archive.writestr(name,data)
        archive.writestr('MANIFEST.sha256',''.join(f'{digest}  {name}\n' for name,digest in sorted(manifest.items())))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise ValueError('ZIP CRC failed')
        for name,digest in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise ValueError('ZIP member verification failed')
    return {'zip':str(output),'files':len(manifest),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'crc_and_member_hashes_verified':True}

if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-only',action='store_true')
    args=parser.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1],args.output,args.source_only),indent=2))
