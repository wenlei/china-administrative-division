"""Build a small, read-only regionCheck release from the verified database."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from managed_areas import build_catalog

ROOT = Path(__file__).resolve().parents[2]


def add_management_catalog(payload, repository=ROOT):
    curated = json.loads((Path(repository) / 'apps/region-check/managed_areas.json').read_text())
    payload['managed_areas'] = build_catalog(payload['records'], payload['target_year'], curated)
    return payload


# Verified whole-territory N->1 county mergers where every physical location in
# old_code moved 100% into the single successor (still safe_conversion=False so
# permission scopes are never silently widened, but point_safe_merge=True for
# station/location alignment). Never include partial-transfer reorganizations.
WHOLE_TERRITORY_MERGED_CODES = frozenset({
    '340208000000',  # 芜湖市三山区 -> 新弋江区 (2020)
    '340203000000',  # 原芜湖市弋江区 -> 新弋江区 (2020)
    '350402000000',  # 三明市梅列区 -> 新三元区 (2021)
    '350403000000',  # 原三明市三元区 -> 新三元区 (2021)
    '410306000000',  # 洛阳市吉利区 -> 孟津区 (2021)
    '410322000000',  # 孟津县 -> 孟津区 (2021)
})


def extract_events(records, repository=ROOT):
    """Build explicit official succession edges from patches/*/xzqh.json."""
    # Only explicit official event patches produce conversion edges. Snapshot
    # code differences and name-stem guesses never produce administrative events.
    events = []
    for path in sorted((Path(repository) / 'patches').glob('*/xzqh.json')):
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
            # A shared remove reason (N -> M) or partial boundary transfer needs parcel/boundary evidence.
            group_size = sum(a['op'] == 'remove' and a.get('reason') == reason
                             for a in operations)
            partial_transfer = any(token in reason for token in ('划归', '部分', '分别'))
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
                                   and old_name is not None and not partial_transfer,
                'point_safe_merge': (op['code'] in WHOLE_TERRITORY_MERGED_CODES
                                     and len(successors) == 1 and not partial_transfer),
                'effective_date': None,
            })
    return events


def apply_extra_patch_updates(payload, repository=ROOT):
    """Apply explicit update operations from updates/2026-10.sources.json extra_patches to target_year records."""
    repo = Path(repository)
    manifest_path = repo / 'updates/2026-10.sources.json'
    if not manifest_path.exists():
        return payload
    manifest = json.loads(manifest_path.read_text())
    target = payload['target_year']
    by_code = {r['code']: r for r in payload['records'] if r['year'] == target}
    supplements = list(payload.get('supplements', []))
    known_supplements = {s.get('patch_file') for s in supplements if isinstance(s, dict)}
    for rel_file in manifest.get('extra_patches', []):
        patch_path = repo / rel_file
        if not patch_path.exists():
            continue
        patch = json.loads(patch_path.read_text())
        meta = patch['meta']
        attribution = {'source_url': meta.get('source_url'), 'notes': meta.get('notes'),
                       'patch_file': rel_file}
        applied = False
        for op in patch.get('operations', []):
            if op.get('op') != 'update':
                continue
            row = by_code.get(op['code'])
            if not row:
                continue
            if op.get('name') and row.get('name') != op['name']:
                row['name'] = op['name']
                applied = True
            if op.get('status') and row.get('status') != op['status']:
                row['status'] = op['status']
                applied = True
            if op.get('new_parent') and row.get('parent_code') != op['new_parent']:
                row['parent_code'] = op['new_parent']
                applied = True
            if applied:
                row['record_source'] = attribution
        if applied and rel_file not in known_supplements:
            supplements.append(attribution)
            known_supplements.add(rel_file)
    payload['supplements'] = supplements
    return payload


def augment_release(base, output, repository=ROOT, *, refresh_events=False, apply_extra_patches=False):
    """Add management relations (and optionally refresh official events / extra patch updates)."""
    from region_check import RegionIndex
    base, output = Path(base), Path(output)
    if output.exists():
        raise ValueError('Output already exists; build into a new release directory')
    RegionIndex(base)  # Check the exact source release before using any of its records.
    payload = json.loads((base / 'regions.json').read_text())
    if apply_extra_patches:
        payload = apply_extra_patch_updates(payload, repository)
    payload = add_management_catalog(payload, repository)
    if refresh_events:
        payload['events'] = extract_events(payload['records'], repository)
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    manifest = json.loads((base / 'manifest.json').read_text())
    manifest.update(sha256=hashlib.sha256(data).hexdigest(),
                    event_count=len(payload['events']),
                    managed_catalog_edition=payload['managed_areas']['edition'],
                    managed_area_count=len(payload['managed_areas']['areas']))
    output.mkdir(parents=True)
    (output / 'regions.json').write_bytes(data)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    RegionIndex(output)  # Fail before publication if a source, member or parent is invalid.
    return manifest['sha256']


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
    events = extract_events(records, repository)
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
    add_management_catalog(payload, repository)
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--database')
    source.add_argument('--base-release')
    parser.add_argument('--output', required=True)
    parser.add_argument('--refresh-events', action='store_true')
    parser.add_argument('--apply-extra-patches', action='store_true')
    args = parser.parse_args()
    print(augment_release(args.base_release, args.output,
                          refresh_events=args.refresh_events,
                          apply_extra_patches=args.apply_extra_patches)
          if args.base_release else build(args.database, args.output))
