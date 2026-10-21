"""Build a small, read-only regionCheck release from the verified database."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build(database, output, repository=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError('Output already exists; build into a new release directory')
    manifest = json.loads((repository / 'updates/2026-10.sources.json').read_text())
    target = manifest['target_year']
    source = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    records = [dict(r) for r in source.execute(
        'SELECT code,name,level,parent_code,year,status FROM divisions '
        'WHERE level<=4 ORDER BY year,code')]
    source.close()
    current = {r['code']: r for r in records if r['year'] == target and r['status'] == 'active'
               and r['code'][:2] in {p['province'] for p in manifest['provinces']}}
    if len(current) != 41989:
        raise ValueError(f'Expected verified 41989 current nodes, found {len(current)}')
    for row in current.values():
        if row['parent_code'] and row['parent_code'] not in current:
            raise ValueError('Active parent missing: ' + row['code'])
    # Only explicit official event patches produce conversion edges. Snapshot
    # code differences and name-stem guesses never produce administrative events.
    events = []
    for path in sorted((repository / 'patches').glob('*/xzqh.json')):
        patch = json.loads(path.read_text())
        if patch['meta'].get('source_pipeline') != 'xzqh':
            continue
        operations = patch['operations']
        for op in operations:
            if op['op'] != 'remove' or not op.get('reason'):
                continue
            reason = op['reason']
            successors = [a for a in operations if a['op'] == 'add' and a['name'] in reason
                          and a['code'][:4] == op['code'][:4]]
            names = re.split(r'[、，,]', re.split(r'[，,]?设立', reason)[0]
                             .removeprefix('撤销').removeprefix('县级'))
            names = [n.removeprefix('县级') for n in names if n]
            # A shared remove reason (N -> M) needs parcel/boundary evidence.
            group_size = sum(a['op'] == 'remove' and a.get('reason') == reason
                             for a in operations)
            old_names = {r['name'] for r in records if r['code'] == op['code']
                         and r['year'] <= int(path.parent.name)}
            old_name = next((n for n in names if n in old_names), None)
            if old_name is None and len(names) == 1:
                old_name = names[0]
            events.append({
                'year': int(path.parent.name), 'old_code': op['code'],
                'old_name': old_name, 'old_name_candidates': names,
                'successors': [{'code': a['code'], 'name': a['name'],
                                'level': a['level'], 'parent_code': a['parent_code']}
                               for a in successors],
                'reason': reason, 'source_url': patch['meta'].get('source_url'),
                'patch_file': str(path.relative_to(repository)),
                'safe_conversion': group_size == 1 and len(successors) == 1
                                   and old_name is not None,
                'effective_date': None,
            })
    supplements = []
    record_sources = {}
    for file in [p['patch'] for p in manifest['provinces']] + manifest['extra_patches']:
        patch = json.loads((repository / file).read_text())
        meta = patch['meta']
        attribution = {'source_url': meta.get('source_url'), 'notes': meta.get('notes'),
                       'patch_file': file}
        for operation in patch['operations']:
            if operation['op'] != 'remove':
                record_sources[operation['code']] = attribution
        if file in manifest['extra_patches']:
            supplements.append(attribution)
    for record in records:
        if record['year'] == target and record['code'] in current:
            record['record_source'] = record_sources.get(record['code'])
            record['code_system'] = 'mca_2026'
        else:
            record['code_system'] = 'nbs_2023' if record['year'] == 2023 else 'historical_mixed'
    provinces = [{k: p.get(k) for k in ('province', 'name', 'url', 'as_of', 'checked_at')}
                 for p in manifest['provinces']]
    payload = {'edition': manifest['edition'], 'target_year': target,
               'snapshot_years': sorted({r['year'] for r in records}),
               'current_count': len(current), 'provinces': provinces, 'supplements': supplements,
               'records': records, 'events': events,
               'limitations': ['Province source dates differ; not a nationwide same-day snapshot.',
                               'Only levels 1-4 are matched; village and street text is preserved.',
                               'Event year is not an exact approval or effective date.',
                               'Historical patches are incomplete; no event does not mean no change.']}
    output.mkdir(parents=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    (output / 'regions.json').write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (output / 'manifest.json').write_text(json.dumps(
        {'sha256': digest, 'edition': payload['edition'], 'current_count': len(current),
         'snapshot_years': payload['snapshot_years'], 'event_count': len(events)}, indent=2))
    return digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(build(args.database, args.output))
