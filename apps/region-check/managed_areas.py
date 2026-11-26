"""Business management areas, kept separate from legal administrative nodes."""
import itertools
import re
import unicodedata
from urllib.parse import urlsplit


AREA_NAME = re.compile(r'开发区|新区|高新区|工业园|产业园|管理区|管委会|示范区|实验区|风景区|投资区|台创园|保税区|保税港|出口加工区|产业集聚区|科技园|合作区|旅游度假区')
GENERIC_NAME = re.compile(r'^(?:经济(?:技术)?开发区|开发区|高新区|新区|工业园区|管理区|示范区|台商投资区|台创园)$')
AREA_TYPES = frozenset({'development_zone', 'new_area', 'managed_subdistrict', 'industrial_park', 'functional_zone'})
VALID_RELATIONS = frozenset({
    'coextensive_management', 'managed_union', 'administered_within',
    'mapping_required', 'historical_reference',
})
_DATE_RE = re.compile(r'^\d{4}(?:-\d{2}(?:-\d{2})?)?$')


def clean(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value))


def _infer_area_type(name, level=None):
    if level == 4 or any(tok in name for tok in ('办事处', '街道', '社区')):
        return 'managed_subdistrict'
    if any(tok in name for tok in ('新区', '实验区', '示范区')):
        return 'new_area'
    if any(tok in name for tok in ('工业园', '产业园', '创业园', '科技园', '台创园')):
        return 'industrial_park'
    if any(tok in name for tok in ('开发区', '高新区', '投资区', '保税')):
        return 'development_zone'
    return 'functional_zone'


def _scope_semantics(relation, verified):
    if not verified:
        return 'unverified'
    if relation == 'administered_within':
        return 'legal_container_only'
    return 'exact_legal_union'


def _valid_date_or_none(value):
    return value is None or (isinstance(value, str) and bool(_DATE_RE.fullmatch(value)))


def build_catalog(records, target_year, curated):
    """Retain known statistical areas as unresolved references, never as live scopes."""
    current = {r['code']: r for r in records if r['year'] == target_year and r['status'] == 'active'}
    old = {r['code']: r for r in records if r['year'] == 2023 and r['status'] == 'active'}
    areas = list(curated['areas'])
    replaced = {code for area in areas for code in area.get('legacy_codes', [])}
    current_names = {(r['parent_code'], r['name']) for r in current.values()}
    for row in old.values():
        if (not AREA_NAME.search(row['name']) or row['code'] in replaced
                or (row['parent_code'], row['name']) in current_names):
            continue
        parent, seen = old.get(row['parent_code']), set()
        while parent and parent['code'] not in seen:
            seen.add(parent['code'])
            live = current.get(parent['code'])
            if live and live['name'] == parent['name']:
                break
            parent = old.get(parent['parent_code'])
        if not parent or parent['code'] not in current:
            continue
        areas.append({'id': 'nbs-2023-' + row['code'], 'name': row['name'], 'aliases': [],
                      'area_type': _infer_area_type(row['name'], row.get('level')),
                      'parent_code': parent['code'], 'scope_codes': [], 'verified': False,
                      'relation': 'historical_reference', 'legacy_codes': [row['code']],
                      'effective_from': None, 'effective_to': None, 'verified_at': None,
                      'sources': [{'url': 'https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/',
                                   'title': '国家统计局2023统计用区划基线', 'as_of': '2023'}],
                      'note': '历史统计名称仍可检索；退出民政现行视图不代表该管理区域已撤销，现行范围尚待核实。'})
    return {'version': 1, 'edition': curated['edition'], 'areas': areas}


class ManagedAreas:
    def __init__(self, index, catalog):
        self.index = index
        if catalog.get('version') != 1 or not isinstance(catalog.get('edition'), str):
            raise ValueError('Invalid managed area catalog')
        self.edition = catalog['edition']
        self.areas, self.aliases = [], {}
        ids = set()
        for original in catalog.get('areas', []):
            area = dict(original)
            area_type = area.get('area_type') or _infer_area_type(area.get('name', ''))
            effective_from = area.get('effective_from')
            effective_to = area.get('effective_to')
            verified_at = area.get('verified_at')
            legacy_codes = area.get('legacy_codes', [])
            if (not isinstance(area.get('id'), str) or area['id'] in ids
                    or not isinstance(area.get('name'), str) or not area['name']
                    or area_type not in AREA_TYPES
                    or type(area.get('verified')) is not bool
                    or area.get('parent_code') not in index.current
                    or index.current[area['parent_code']]['level'] > 3
                    or area.get('relation') not in VALID_RELATIONS
                    or not _valid_date_or_none(effective_from)
                    or not _valid_date_or_none(effective_to)
                    or not _valid_date_or_none(verified_at)
                    or not isinstance(legacy_codes, list)
                    or not all(isinstance(c, str) and re.fullmatch(r'\d{12}', c) for c in legacy_codes)
                    or not isinstance(area.get('note'), str)
                    or not isinstance(area.get('scope_codes'), list)
                    or not isinstance(area.get('sources'), list) or not area['sources']):
                raise ValueError('Invalid managed area')
            area['area_type'] = area_type
            area['effective_from'] = effective_from
            area['effective_to'] = effective_to
            area['verified_at'] = verified_at
            area['legacy_codes'] = list(legacy_codes)
            area['scope_semantics'] = _scope_semantics(area['relation'], area['verified'])
            ids.add(area['id'])
            for source in area['sources']:
                url = urlsplit(source.get('url', ''))
                if url.scheme not in ('https', 'http') or not url.hostname or url.username:
                    raise ValueError('Invalid managed area source')
            codes = area['scope_codes']
            if (len(codes) != len(set(codes)) or len(codes) > 100
                    or area['verified'] != bool(codes)):
                raise ValueError('Managed area scope must be explicit')
            if area['verified'] and area['relation'] not in {'coextensive_management', 'managed_union', 'administered_within'}:
                raise ValueError('Verified managed area must use an explicit mapping relation')
            if not area['verified'] and area['relation'] not in {'mapping_required', 'historical_reference'}:
                raise ValueError('Unverified managed area must use mapping_required or historical_reference')
            for code in codes:
                if (code not in index.current or index.current[code]['level'] <= index.current[area['parent_code']]['level']
                        or area['parent_code'] not in {n['code'] for n in index.paths[code]}):
                    raise ValueError('Managed area scope is outside its parent')
            area['parent_path'] = [{k: n[k] for k in ('code', 'name', 'level')}
                                   for n in index.paths[area['parent_code']]]
            area['scopes'] = [index.describe(code)['path'] for code in codes]
            names = list(dict.fromkeys([area['name']] + area.get('aliases', [])))
            if any(not isinstance(n, str) or not 2 <= len(n) <= 100 or '/' in n for n in names):
                raise ValueError('Invalid managed area alias')
            for name in names:
                self.aliases.setdefault(clean(name), []).append(area)
            self.areas.append(area)

    @staticmethod
    def _bridge(area, scopes):
        return {
            'legal_standard': 'GB/T 2260 + GB/T 10114',
            'legal_target_levels': sorted({p[-1]['level'] for p in scopes}),
            'nbs_statistical_codes': list(area['legacy_codes']),
            'area_type': area['area_type'],
            'scope_semantics': area['scope_semantics'],
        }

    @staticmethod
    def _prefixes(path):
        options = []
        for node in path:
            name = node['name']
            values = ['', name]
            short = re.sub(r'[省市]$', '', name) if node['level'] <= 2 or name.endswith('市') else name
            if short != name:
                values.append(short)
            options.append(values)
        return {''.join(values) for values in itertools.product(*options)}

    def match(self, address):
        text, hits = clean(address), []
        for alias, areas in self.aliases.items():
            start = text.find(alias)
            if start < 0:
                continue
            prefix, suffix = text[:start], text[start + len(alias):]
            for area in areas:
                path = area['parent_path']
                if prefix not in self._prefixes(path):
                    continue
                if GENERIC_NAME.fullmatch(alias) and not any(prefix.endswith(n)
                        for n in (path[-1]['name'], re.sub(r'市$', '', path[-1]['name']))):
                    continue
                hits.append((len(alias), area, alias, suffix))
        if not hits:
            return None
        # Longer explicit names beat a generic substring, within the same parent.
        best = max(h[0] for h in hits)
        chosen = {h[1]['id']: h for h in hits if h[0] == best}
        matches = []
        for _, area, alias, suffix in chosen.values():
            scopes = area['scopes']
            status = 'verified' if area['verified'] else 'mapping_required'
            if suffix and scopes:
                exact = [p for p in scopes if clean(p[-1]['name']) == suffix]
                if exact:
                    scopes, suffix = exact, ''
                else:
                    # Never discard an unrecognized town and grant the whole managed area.
                    scopes, status = [], 'partial'
            matches.append({k: area[k] for k in ('id', 'name', 'area_type', 'parent_code', 'parent_path',
                                                 'relation', 'scope_semantics', 'legacy_codes',
                                                 'effective_from', 'effective_to', 'verified_at',
                                                 'sources', 'note')} |
                           {'matched_name': alias, 'status': status, 'scope_paths': scopes,
                            'standard_bridge': self._bridge(area, scopes),
                            'unparsed_suffix': suffix, 'catalog_edition': self.edition})
        return {'status': 'ambiguous' if len(matches) > 1 else matches[0]['status'],
                'candidate_total': len(matches), 'matches': matches[:5],
                'catalog_edition': self.edition}

    def search(self, query, limit):
        text = clean(query)
        return [{k: area[k] for k in ('id', 'name', 'area_type', 'parent_path', 'relation',
                                      'scope_semantics', 'legacy_codes', 'effective_from',
                                      'effective_to', 'verified_at', 'sources', 'note')} |
                {'status': 'verified' if area['verified'] else 'mapping_required',
                 'scope_paths': area['scopes'],
                 'standard_bridge': self._bridge(area, area['scopes'])}
                for area in self.areas if any(text in clean(name) for name in [area['name']] + area.get('aliases', []))][:limit]
