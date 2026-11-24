#!/usr/bin/env python3
"""Back up code replacements and add versioned artifacts without touching raw data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from safe_merge import apply, plan, check_chain

VERSION='2.6.0'
ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def install(target, execute=False):
    target=target.expanduser().absolute();check_chain(target)
    config={'version':VERSION,'url_model':f'models/releases/{VERSION}/url-model.json','vision_model':f'models/releases/{VERSION}/vision-model.pt','reports':f'reports/releases/{VERSION}'}
    artifacts=[]
    for folder,source in [('models',ROOT/'models/trained'),('reports',ROOT/'reports')]:
        for src in sorted(source.rglob('*')):
            if not src.is_file() or src.suffix not in {'.json','.pt','.md','.csv'}:continue
            if src.is_symlink():raise ValueError('Artifact symlink refused')
            dst=target/folder/'releases'/VERSION/src.relative_to(source);check_chain(dst)
            digest=sha(src)
            if dst.exists() and (not dst.is_file() or sha(dst)!=digest):raise ValueError(f'Existing versioned artifact differs; refused: {dst}')
            artifacts.append((src,dst,digest))
    with tempfile.TemporaryDirectory(prefix='pg-code-merge-') as temporary:
        stage=Path(temporary).resolve()/'source';stage.mkdir()
        # Copy only merge-allowlisted code, never local datasets or environments.
        from safe_merge import ALLOWED_DIRS,ALLOWED_FILES
        for src in ROOT.iterdir():
            if src.name in ALLOWED_DIRS and src.is_dir():
                shutil.copytree(src,stage/src.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','node_modules'))
            elif src.name in ALLOWED_FILES and src.is_file():shutil.copy2(src,stage/src.name)
        (stage/'config').mkdir(exist_ok=True)
        (stage/'config/local-install.json').write_text(json.dumps(config,indent=2)+'\n')
        operations,conflicts=plan(stage,target,replace=True)
        result={'target':str(target),'code_operations':len(operations),'artifact_files':len(artifacts),'protected':['data','.env','.git','.venv','existing models','existing reports'],'mode':'preview'}
        if execute:
            target.mkdir(parents=True,exist_ok=True)
            for src,dst,digest in artifacts:
                if dst.exists():continue
                dst.parent.mkdir(parents=True,exist_ok=True)
                with dst.open('xb') as out,src.open('rb') as inp:shutil.copyfileobj(inp,out)
                if sha(dst)!=digest:raise ValueError('Artifact verification failed')
            result.update(apply(stage,target,replace=True));result['mode']='applied'
        return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path,default=Path.home()/'Desktop/PhishGuard')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();print(json.dumps(install(args.target,args.apply),indent=2))
