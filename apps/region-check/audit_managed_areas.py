"""Read-only national statistical-name difference and management-scope audit."""
import argparse
import json
from collections import Counter
from pathlib import Path

from region_check import RegionIndex
from managed_areas import AREA_NAME


def audit(directory):
    index = RegionIndex(directory)
    areas = index.managed_areas.areas
    current_names = {(r['parent_code'], r['name']) for r in index.current.values()}
    by_legacy = {code: area for area in areas for code in area.get('legacy_codes', [])}
    legacy = []
    for row in index.data['records']:
        if row['year'] != 2023 or row['status'] != 'active' or not AREA_NAME.search(row['name']):
            continue
        area = by_legacy.get(row['code'])
        status = ('current_administrative' if (row['parent_code'], row['name']) in current_names
                  else 'verified_scope' if area and area['verified']
                  else 'mapping_required' if area else 'unresolved_parent_reference')
        legacy.append({'code': row['code'], 'name': row['name'], 'parent_code': row['parent_code'],
                       'year': 2023, 'status': status})
    cases = []
    for case in json.loads(Path(__file__).with_name('managed_area_cases.json').read_text()):
        response = index.match(case['input'])
        managed = response.get('managed_areas', {})
        matches = managed.get('matches', [])
        scopes = matches[0]['scope_paths'] if len(matches) == 1 else []
        cases.append({**case, 'actual': managed.get('status'),
                      'passed': managed.get('status') == case['expected'],
                      'area_id': matches[0]['id'] if len(matches) == 1 else None,
                      'administrative_paths': ['/'.join(n['name'] for n in path) for path in scopes],
                      'sources': matches[0]['sources'] if len(matches) == 1 else []})
    return {'data_sha256': index.digest, 'catalog_edition': index.managed_areas.edition,
            'current_administrative_nodes': len(index.current),
            'managed_reference_count': len(areas), 'verified_count': sum(a['verified'] for a in areas),
            'mapping_required_count': sum(not a['verified'] for a in areas),
            'national_historical_candidates': len(legacy), 'national_status_counts': dict(Counter(r['status'] for r in legacy)),
            'cases_passed': all(c['passed'] for c in cases), 'case_count': len(cases), 'cases': cases,
            'historical_candidates': legacy,
            'limits': ['Candidate scan is based on known 2023 names, not a complete current national management-area register.',
                       'Historical recognition does not prove the current boundary or continued existence.',
                       'Only explicitly verified scopes may become saved administrative paths.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.data)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('cases', 'historical_candidates', 'limits')}, ensure_ascii=False))
    raise SystemExit(0 if result['cases_passed'] else 1)
