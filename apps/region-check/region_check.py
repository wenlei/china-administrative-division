"""Read-only administrative name history and address matching. No external calls."""
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from managed_areas import ManagedAreas

VERSION = '0.1.3'


class CurrentTreeUnavailable(Exception):
    """The current catalog cannot provide a complete, valid parent chain."""


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value))


def normalize_code(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:\d{6}|\d{9}|\d{12})', value):
        raise ValueError('code must contain 6, 9, or 12 digits')
    return value.ljust(12, '0')


class RegionIndex:
    def __init__(self, directory):
        directory = Path(directory)
        data = (directory / 'regions.json').read_bytes()
        manifest = json.loads((directory / 'manifest.json').read_text())
        if hashlib.sha256(data).hexdigest() != manifest['sha256']:
            raise ValueError('Data checksum mismatch')
        self.data = json.loads(data)
        self.digest = manifest['sha256']
        self.year = self.data['target_year']
        self.provinces = {p['province']: p for p in self.data['provinces']}
        self.current = {r['code']: r for r in self.data['records']
                        if r['year'] == self.year and r['status'] == 'active'
                        and r['code'][:2] in self.provinces}
        self.snapshots = defaultdict(list)
        for row in self.data['records']:
            self.snapshots[row['code']].append(row)
        self.paths = {code: self._path(row) for code, row in self.current.items()}
        self.exact_current_paths = defaultdict(list)
        for code, path in self.paths.items():
            levels = [node['level'] for node in path]
            if (levels in ([1, 2], [1, 2, 3], [1, 2, 4], [1, 2, 3, 4]) and not path[0]['parent_code']
                    and path[0]['code'][:2] == code[:2]):
                self.exact_current_paths[''.join(node['name'] for node in path)].append(code)
        self.names = defaultdict(set)
        for row in self.current.values():
            if len(row['name']) >= 2:
                self.names[row['name']].add(row['code'])
            # Only province/prefecture suffix abbreviations. Never abbreviate a
            # county/town into a generic word or treat road numbers as towns.
            if row['level'] in (1, 2):
                short = re.sub(r'(省|市)$', '', row['name'])
                if len(short) >= 2:
                    self.names[short].add(row['code'])
        self.alias_events = defaultdict(list)
        for event in self.data['events']:
            for old_name in event.get('old_name_candidates', []):
                if len(old_name) >= 2:
                    self.alias_events[old_name].append(event)
        self.historical_names = defaultdict(list)
        for records in self.snapshots.values():
            for row in records:
                if row['year'] != self.year and len(row['name']) >= 2:
                    self.historical_names[row['name']].append(row)
        self.all_names = set(self.names) | set(self.alias_events) | set(self.historical_names)
        self.lengths = sorted({len(n) for n in self.all_names})
        self.managed_areas = ManagedAreas(self, self.data.get('managed_areas',
            {'version': 1, 'edition': self.data['edition'], 'areas': []}))

    def _path(self, row):
        path, seen = [], set()
        while row:
            if row['code'] in seen:
                raise ValueError('Parent cycle')
            seen.add(row['code'])
            path.append(row)
            row = self.current.get(row['parent_code'])
        return list(reversed(path))

    def summary(self):
        return {'service': 'regionCheck', 'version': VERSION, 'edition': self.data['edition'],
                'target_year': self.year, 'snapshot_years': self.data['snapshot_years'],
                'current_count': len(self.current), 'event_count': len(self.data['events']),
                'managed_catalog_edition': self.managed_areas.edition,
                'managed_catalog_loaded': 'managed_areas' in self.data,
                'managed_area_count': len(self.managed_areas.areas),
                'managed_verified_count': sum(a['verified'] for a in self.managed_areas.areas),
                'data_sha256': self.digest, 'provinces': self.data['provinces'],
                'supplements': self.data.get('supplements', []),
                'limitations': self.data['limitations']}

    def division_tree(self):
        """Return the complete current directory, never historical aliases.

        Code order determines stable output order. Names are unique within their
        parent in this name-only contract; children of duplicate names are merged.
        A broken current parent chain fails the whole request. Prefecture-direct
        towns use their own list and retain level 4, without inventing a county.
        """
        provinces = {}
        for code, row in sorted(self.current.items()):
            level = row.get('level')
            if type(level) is not int or not 1 <= level <= 4:
                continue
            path = self.paths[code]
            levels = [node.get('level') for node in path]
            direct_town = levels == [1, 2, 4]
            if ((levels != list(range(1, level + 1)) and not direct_town)
                    or path[0]['code'][:2] != code[:2]):
                raise CurrentTreeUnavailable('Invalid current administrative parent chain')
            for depth, node in enumerate(path, 1):
                parent = path[depth - 2]['code'] if depth > 1 else None
                if (node.get('parent_code') != parent
                        or node.get('year') != self.year or node.get('status') != 'active'
                        or self.current.get(node['code']) is not node
                        or not isinstance(node.get('name'), str) or not node['name'].strip()):
                    raise CurrentTreeUnavailable('Invalid current administrative parent chain')
            province = provinces.setdefault(path[0]['name'], {'cities': {}})
            if level == 1:
                continue
            city = province['cities'].setdefault(path[1]['name'], {'districts': {}, 'direct_towns': {}})
            if level == 2:
                continue
            if direct_town:
                city['direct_towns'].setdefault(path[2]['name'], None)
                continue
            towns = city['districts'].setdefault(path[2]['name'], {})
            if level == 4:
                towns.setdefault(path[3]['name'], None)
        data = [{'province': province, 'cities': [
            {'city': city, 'districts': list(values['districts']),
             'towns': {district: list(towns) for district, towns in values['districts'].items()},
             'direct_towns': list(values['direct_towns'])}
            for city, values in item['cities'].items()]}
            for province, item in provinces.items()]
        return {'data': data, 'edition': self.data['edition'], 'target_year': self.year,
                'data_sha256': self.digest, 'current_only': True,
                'excluded_incomplete_paths': 0}

    def related_events(self, path):
        # Attach changes to the matched unit AND its ancestors, even when the
        # input already uses today's name. Seed only explicit name+code pairs.
        by_code = {r['code']: r for r in path}
        events = []
        related = set()
        for event in self.data['events']:
            links = event['successors'] + [{'code': event['old_code'], 'name': event['old_name']}]
            if any(link['code'] in by_code and link['name'] == by_code[link['code']]['name']
                   for link in links):
                events.append(event)
                related.update(link['code'] for link in links)
        changed = True
        while changed:
            changed = False
            for event in self.data['events']:
                links = {event['old_code']} | {s['code'] for s in event['successors']}
                if links & related and event not in events:
                    events.append(event)
                    related.update(links)
                    changed = True
        return sorted(events, key=lambda e: (e['year'], e['old_code']))

    def describe(self, code):
        row = self.current[code]
        path = self.paths[code]
        return {**row, 'path': [{k: r[k] for k in ('code', 'name', 'level')} for r in path],
                'administrative_address': ''.join(r['name'] for r in path),
                'related_events': self.related_events(path),
                'source': {**self.provinces[code[:2]],
                           'record_source': row.get('record_source')}, 'code_system': 'mca_2026'}

    def occurrences(self, address, include_history=True):
        hits = []
        for start in range(len(address)):
            for length in self.lengths:
                name = address[start:start + length]
                if len(name) == length and name in (self.all_names if include_history else self.names):
                    hits.append((start, start + length, name))
        # Suppress short nested names, e.g. 河南 inside 河南省, and name pieces
        # embedded in a longer known county/town name.
        return [h for h in hits if not any(a <= h[0] and b >= h[1] and b-a > h[1]-h[0]
                                          for a, b, _ in hits)]

    def _successors(self, event, seen=None):
        seen = set() if seen is None else set(seen)
        key = (event['year'], event['old_code'])
        if key in seen:
            return []
        seen.add(key)
        out = []
        for successor in event['successors']:
            code = successor['code']
            # Check a subsequent event before accepting a reused current code.
            later = [e for e in self.data['events']
                     if e['old_code'] == code and e['year'] > event['year']]
            if later:
                for e in later:
                    out.extend(self._successors(e, seen))
            elif code in self.current and self.current[code]['name'] == successor['name']:
                out.append((code, [event], event['safe_conversion']))
        # Carry every conversion edge and its ambiguity through the chain.
        result = []
        for code, chain, safe in out:
            if chain[0] is not event:
                result.append((code, [event] + chain, safe and event['safe_conversion']))
            else:
                result.append((code, chain, safe))
        return result

    def search(self, query, limit=20):
        q = normalize(query)
        if not 2 <= len(q) <= 100:
            raise ValueError('q must contain 2 to 100 characters')
        candidates = {}
        for name, codes in self.names.items():
            if q in name or (q.isdigit() and any(c.startswith(q) for c in codes)):
                for code in codes:
                    candidates[code] = {**self.describe(code), 'matched_name': name,
                                        'match_type': 'current', 'rank': 0 if q == name else 1}
        historical = []
        for name, events in self.alias_events.items():
            if q not in name and not any(e['old_code'].startswith(q) for e in events):
                continue
            for event in events:
                targets = self._successors(event)
                historical.append({'name': name, 'code': event['old_code'], 'event': event,
                                   'current_candidates': [self.describe(c) for c, _, _ in targets]})
        results = sorted(candidates.values(), key=lambda r: (r['rank'], r['level'], r['code']))
        # Include historical snapshot names even without an event-to-present link.
        snapshot_matches = []
        for code, records in self.snapshots.items():
            for row in records:
                if row['year'] != self.year and (q in row['name'] or code.startswith(q)):
                    snapshot_matches.append({**row, 'conversion_verified': False})
        return {'query': query, 'current': results[:limit], 'current_total': len(results),
                'managed_areas': self.managed_areas.search(query, limit),
                'historical': historical[:limit], 'historical_total': len(historical),
                'snapshot_matches': snapshot_matches[:limit],
                'snapshot_total': len(snapshot_matches)}

    def history(self, value):
        code = normalize_code(value)
        related, pending = {code}, [code]
        events = []
        while pending:
            at = pending.pop()
            for e in self.data['events']:
                links = {e['old_code']} | {s['code'] for s in e['successors']}
                if at in links and e not in events:
                    events.append(e)
                    for other in links - related:
                        related.add(other)
                        pending.append(other)
        snapshots = [r for key in related for r in self.snapshots.get(key, [])]
        if not snapshots and not events:
            raise KeyError(code)
        return {'code': code, 'events': sorted(events, key=lambda e: (e['year'], e['old_code'])),
                'snapshots': sorted(snapshots, key=lambda r: (r['year'], r['code'])),
                'current_candidates': [self.describe(c) for c in sorted(related) if c in self.current],
                'snapshot_differences_are_events': False,
                'history_complete': False, 'snapshot_years': self.data['snapshot_years'],
                'notes': ['Snapshots use different code systems. Same code does not prove entity identity.',
                          'No event found does not prove the division never changed.']}

    def match(self, address, limit=5):
        result = self._match_administrative(address, limit)
        result['managed_catalog_loaded'] = bool(self.managed_areas.areas)
        result['managed_catalog_edition'] = self.managed_areas.edition
        areas = self.managed_areas.match(address)
        if areas:
            result['managed_areas'] = areas
            # Administrative candidates retain their actual codes and parent chains.
            # The business scope may be a union, and is never a fictional county.
            if areas['status'] == 'verified':
                result['status'] = 'managed'
            message = {'verified': '已识别管理区域；请使用managed_areas中的核定范围。',
                       'partial': '管理区域已识别，余下具体地址尚未完全识别，请保留原文核查。',
                       'ambiguous': '存在多个同名管理区域，请补充上级地区。',
                       'mapping_required': '管理区域名称已识别，系统管辖范围映射尚待核实；不代表人员填写错误。'}
            result['warnings'] = list(result.get('warnings', [])) + [message[areas['status']]]
        return result

    def _match_administrative(self, address, limit=5):
        if not isinstance(address, str) or not 2 <= len(address.strip()) <= 1000:
            raise ValueError('address must contain 2 to 1000 characters')
        text = normalize(address)
        exact = self.exact_current_paths.get(text, [])
        if len(exact) == 1:
            # A unique whole current path is stronger than a county-name fragment
            # spanning two valid names, e.g. 中山市 + 南区街道 contains 市南区,
            # or 天津市 + 市辖区 contains 津市市.
            # No prefix/suffix, shorthand, historical name or incomplete path is
            # accepted here; all other input keeps the normal conflict checks.
            code = exact[0]
            path = self.paths[code]
            level = self.current[code]['level']
            status = 'matched' if level == 4 else 'partial'
            suggested = (''.join(node['name'] for node in path if node['name'] not in
                         ('市辖区', '县', '省直辖县级行政区划', '自治区直辖县级行政区划'))
                         if level == 4 else None)
            warnings = (['Only part of the administrative path was resolved; original address must be retained.']
                        if level < 4 else [])
            candidate = {**self.describe(code), 'status': status, 'matched_level': level,
                         'match_method': 'current_name', 'evidence': [],
                         'unmatched_prefix': '', 'unparsed_suffix': '', 'matched_text': text,
                         'suggested_address': suggested,
                         'automatic_conversion': False}
            return {'input': address, 'normalized_input': text, 'status': status,
                    'candidate_total': 1, 'candidates': [candidate], 'warnings': warnings,
                    'edition': self.data['edition'], 'historical_unresolved': [], 'unresolved_events': [],
                    'history_complete': False, 'village_verified': False}
        direct = self._match(address, limit, include_history=False)
        if direct['status'] == 'matched':
            return direct
        return self._match(address, limit, include_history=True)

    def _match(self, address, limit=5, include_history=True):
        if not isinstance(address, str) or not 2 <= len(address.strip()) <= 1000:
            raise ValueError('address must contain 2 to 1000 characters')
        text = normalize(address)
        occurrences = self.occurrences(text, include_history)
        evidence = []
        for start, end, name in occurrences:
            for code in self.names.get(name, []):
                evidence.append({'code': code, 'start': start, 'end': end, 'name': name,
                                 'events': [], 'safe': True})
            for event in (self.alias_events.get(name, []) if include_history else []):
                for code, chain, safe in self._successors(event):
                    evidence.append({'code': code, 'start': start, 'end': end, 'name': name,
                                     'events': chain, 'safe': safe})
        candidates = []
        for code in {e['code'] for e in evidence}:
            path = self.paths[code]
            codes = {r['code'] for r in path}
            chosen = [e for e in evidence if e['code'] in codes]
            levels = {self.current[e['code']]['level'] for e in chosen}
            # Explicit higher-level names must agree with the candidate branch.
            conflict = False
            for level in (1, 2, 3):
                anchors = [e for e in evidence if self.current[e['code']]['level'] == level]
                if anchors and level <= self.current[code]['level']:
                    if not any(e['code'] in codes for e in anchors):
                        conflict = True
            if conflict:
                continue
            # A path must occur in parent-to-child text order.
            positions = [(self.current[e['code']]['level'], e['start']) for e in chosen]
            if any(l1 < l2 and p1 > p2 for l1, p1 in positions for l2, p2 in positions):
                continue
            score = sum(level * 100 for level in levels) + sum(len(e['name']) for e in chosen)
            candidates.append((score, code, chosen))
        candidates.sort(key=lambda x: (-x[0], x[1]))
        # Parent-only results are subsumed by a more specific compatible path.
        leaves = [v for v in candidates if not any(
            v[1] != other[1] and v[1] in {r['code'] for r in self.paths[other[1]]}
            for other in candidates)]
        results = []
        for score, code, chosen in leaves[:limit]:
            events = []
            for e in chosen:
                for event in e['events']:
                    if event not in events:
                        events.append(event)
            safe = all(e['safe'] for e in chosen)
            end = max(e['end'] for e in chosen)
            residual = text[end:]
            matched = ''.join(text[i] for i in range(end)
                              if any(e['start'] <= i < e['end'] for e in chosen))
            unmatched_prefix = ''.join(text[i] for i in range(end)
                                      if not any(e['start'] <= i < e['end'] for e in chosen))
            # Unrecognized county/town-looking tokens must never be silently
            # discarded when constructing a suggested address.
            unresolved = bool(re.search(r'[^省市区县镇乡街道]{1,15}(?:县|区|镇|乡|街道)',
                                        unmatched_prefix + residual))
            level = self.current[code]['level']
            if not safe or unmatched_prefix:
                status = 'needs_review'
            elif level < 4 or unresolved:
                status = 'partial'
            else:
                status = 'historical' if events else 'matched'
            item = {**self.describe(code), 'status': status, 'matched_level': level,
                    'match_method': 'official_event' if events else 'current_name',
                    'evidence': events, 'unmatched_prefix': unmatched_prefix,
                    'unparsed_suffix': residual, 'matched_text': matched,
                    'suggested_address': None, 'automatic_conversion': status == 'historical'}
            if status in ('matched', 'historical'):
                # Synthetic municipality grouping nodes are omitted in addresses.
                parts = [r['name'] for r in self.paths[code]
                         if r['name'] not in ('市辖区', '县', '省直辖县级行政区划', '自治区直辖县级行政区划')]
                item['suggested_address'] = ''.join(parts) + residual
            results.append(item)
        status = 'unmatched' if not results else ('ambiguous' if len(leaves) > 1 else results[0]['status'])
        if status == 'ambiguous':
            for item in results:
                item['suggested_address'] = None
                item['automatic_conversion'] = False
        pending_events = [event for _, _, name in occurrences
                          for event in (self.alias_events.get(name, []) if include_history else [])
                          if not self._successors(event)]
        historical_unresolved = []
        for _, _, name in occurrences:
            if include_history and name not in self.names and name not in self.alias_events:
                historical_unresolved.extend(self.historical_names.get(name, []))
        warnings = []
        if historical_unresolved or pending_events:
            status = 'needs_review'
            warnings.append('A historical name was found without a verified link to current divisions.')
        if results:
            best_codes = {r['code'] for r in self.paths[leaves[0][1]]}
            higher_conflicts = [e for e in evidence if self.current[e['code']]['level'] <= 3
                                and e['code'] not in best_codes
                                and not any(o['start'] == e['start'] and o['end'] == e['end']
                                            and o['code'] in best_codes for o in evidence)]
            if higher_conflicts and status != 'ambiguous':
                status = 'needs_review'
                warnings.append('Recognized administrative names belong to conflicting paths.')
        if status == 'needs_review':
            for item in results:
                item['suggested_address'] = None
                item['automatic_conversion'] = False
                item['status'] = 'needs_review'
        if status == 'partial':
            warnings.append('Only part of the administrative path was resolved; original address must be retained.')
        if re.search(r'\d+乡道', text):
            warnings.append('Road labels such as 002乡道 are not township names.')
        return {'input': address, 'normalized_input': text, 'status': status,
                'candidate_total': len(leaves), 'candidates': results,
                'warnings': warnings, 'edition': self.data['edition'],
                'historical_unresolved': historical_unresolved[:20],
                'unresolved_events': pending_events[:20],
                'history_complete': False, 'village_verified': False}
