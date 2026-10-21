#!/usr/bin/env python3
"""Compare the active four-level database against every archived official source."""
import argparse
import hashlib
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
    supplements = {}
    for file in manifest.get('extra_patches', []):
        for operation in json.loads((root/file).read_text())['operations']:
            if operation['op'] != 'add':
                raise ValueError('Verifier requires explicit supplement projection for non-add operations')
            supplements[operation['code']] = dict(name=operation['name'], level=operation['level'], parent_code=operation['parent_code'])
    total = 0
    for source in manifest['provinces']:
        if source['status'] != 'included':
            raise ValueError(f"Source not admitted: {source['province']}")
        raw = args.raw/source['file']
        original = args.raw/source.get('original_file', source['file'])
        if hashlib.sha256(original.read_bytes()).hexdigest() != source['sha256'] or hashlib.sha256(raw.read_bytes()).hexdigest() != source['parsed_sha256']:
            raise ValueError(f"Source checksum mismatch: {source['province']}")
        if source['parser'] == 'mca-snapshot':
            entries = module.parse_mca_snapshot(json.loads(raw.read_text()), source['province'], source['expected_towns'], source.get('name_resolutions'))
        else:
            entries = module.parse_table(module.read_rows(raw,source['parser']),source['province'],source['name'],source['expected_towns'])
        # Resolve the same documented historical intermediate nodes used by replay.
        module.build_patch(source, entries, baseline)
        expected = {c.ljust(12,'0'):dict(name=n['name'], level=n['level'], parent_code=n['parent_code'].ljust(12,'0') if n['parent_code'] else None) for c,n in entries.items()}
        expected.update({c:n for c,n in supplements.items() if c.startswith(source['province'])})
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


if __name__ == '__main__':
    main()
