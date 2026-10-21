#!/usr/bin/env python3
"""Compare the active four-level database against every archived official source."""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3

spec = importlib.util.spec_from_file_location('official_update', Path(__file__).with_name('build-official-update.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.sources.read_text())
    db = sqlite3.connect(f'file:{args.database.resolve()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    baseline = db.execute('SELECT * FROM divisions WHERE year=? AND level<=4', (manifest['baseline_year'],)).fetchall()
    if not baseline:
        raise ValueError('Historical baseline missing')
    root = Path(__file__).resolve().parent.parent
    supplements = [operation for file in manifest.get('extra_patches', [])
                   for operation in json.loads((root/file).read_text())['operations']]
    total = 0
    for source in manifest['provinces']:
        if source['status'] != 'included':
            raise ValueError(f"Source not admitted: {source['province']}")
        entries = module.parse_source(source,args.raw)
        # Resolve the same documented historical intermediate nodes used by replay.
        module.build_patch(source, entries, baseline)
        expected = {c.ljust(12,'0'):dict(name=n['name'], level=n['level'], parent_code=n['parent_code'].ljust(12,'0') if n['parent_code'] else None) for c,n in entries.items()}
        expected = project_supplements(expected,supplements,source['province'])
        actual = {row['code']:dict(name=row['name'],level=row['level'],parent_code=row['parent_code']) for row in db.execute("SELECT code,name,level,parent_code FROM divisions WHERE year=? AND level<=4 AND status='active' AND substr(code,1,2)=?", (manifest['target_year'],source['province']))}
        missing = sorted(expected.keys()-actual.keys())
        extra = sorted(actual.keys()-expected.keys())
        changed = [c for c in expected.keys() & actual.keys() if expected[c] != actual[c]]
        if missing or extra or changed:
            raise ValueError(f"{source['name']}: missing={missing[:5]}, extra={extra[:5]}, changed={[(c,expected[c],actual[c]) for c in changed[:5]]}")
        print(f"{source['province']} {source['name']}: {len(actual)} nodes, zero differences")
        total += len(actual)
    print(f'{len(manifest["provinces"])} provinces, {total} four-level nodes: zero differences against archived sources and supplements')
    db.close()


def project_supplements(expected, operations, province):
    expected = {code:dict(row) for code,row in expected.items()}
    for op in operations:
        code=op['code']
        if not code.startswith(province):
            continue
        if op['op']=='add':
            if code in expected:
                raise ValueError(f'Supplement adds existing code: {code}')
            expected[code]=dict(name=op['name'],level=op['level'],parent_code=op['parent_code'])
        elif op['op']=='update' and op.get('status')=='deprecated':
            if code not in expected:
                raise ValueError(f'Supplement withdraws missing code: {code}')
            if any(row['parent_code']==code for row in expected.values()):
                raise ValueError(f'Supplement withdraws parent with active children: {code}')
            del expected[code]
        else:
            raise ValueError(f'Unsupported supplement projection: {op}')
    return expected


if __name__ == '__main__':
    main()
