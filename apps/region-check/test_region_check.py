"""Regression and real HTTP tests; full-data tests use REGION_TEST_DATA."""
import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from region_check import RegionIndex, CurrentTreeUnavailable
from server import BoundedServer


def write_data(directory, payload):
    data = json.dumps(payload, ensure_ascii=False).encode()
    Path(directory, 'regions.json').write_bytes(data)
    Path(directory, 'manifest.json').write_text(json.dumps({'sha256': hashlib.sha256(data).hexdigest()}))


def make_data(directory):
    records = []
    def row(code, name, level, parent=None, year=2026):
        records.append(dict(code=code.ljust(12, '0'), name=name, level=level,
                            parent_code=parent.ljust(12, '0') if parent else None,
                            year=year, status='active'))
    row('410000', '河南省', 1)
    row('410300', '洛阳市', 2, '410000')
    row('410307', '偃师区', 3, '410300')
    row('410307110', '大口镇', 4, '410307')
    row('110000', '北京市', 1)
    row('110100', '市辖区', 2, '110000')
    row('110105', '朝阳区', 3, '110100')
    row('220000', '吉林省', 1)
    row('220100', '长春市', 2, '220000')
    row('220104', '朝阳区', 3, '220100')
    row('500000', '重庆市', 1)
    row('500100', '市辖区', 2, '500000')
    row('500157', '两江新区', 3, '500100')
    row('500157001', '某某街道', 4, '500157')
    row('410307110', '另一个镇', 4, '410307', year=2023)
    event = {'year': 2021, 'old_code': '410381000000', 'old_name': '偃师市',
             'old_name_candidates': ['偃师市'],
             'successors': [{'code': '410307000000', 'name': '偃师区'}],
             'reason': '撤销县级偃师市，设立洛阳市偃师区', 'source_url': 'https://example.gov.cn/event',
             'safe_conversion': True, 'effective_date': None}
    merge = {**event, 'year': 2025, 'old_code': '500105000000', 'old_name': None,
             'old_name_candidates': ['江北区', '渝北区'], 'safe_conversion': False,
             'reason': '撤销江北区、渝北区，设立两江新区',
             'successors': [{'code': '500157000000', 'name': '两江新区'}]}
    payload = {'edition': '2026-10', 'target_year': 2026, 'snapshot_years': [2023, 2026],
               'provinces': [{'province': n, 'name': n, 'as_of': None} for n in ['41','11','22','50']],
               'records': records, 'events': [event, merge], 'limitations': ['Historical coverage incomplete']}
    write_data(directory, payload)


class MatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        make_data(cls.temp.name)
        cls.index = RegionIndex(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_direct_and_residual_preserved(self):
        r = self.index.match('河南省洛阳市偃师区大口镇董村12号')
        self.assertEqual(r['status'], 'matched')
        self.assertEqual(r['candidates'][0]['suggested_address'], r['input'])
        self.assertFalse(r['village_verified'])
        self.assertEqual(r['candidates'][0]['related_events'][0]['old_code'], '410381000000')

    def test_old_name_converts_using_official_event(self):
        r = self.index.match('河南省洛阳市偃师市大口镇董村12号')
        self.assertEqual(r['status'], 'historical')
        candidate = r['candidates'][0]
        self.assertEqual(candidate['suggested_address'], '河南省洛阳市偃师区大口镇董村12号')
        self.assertTrue(candidate['automatic_conversion'])
        self.assertEqual(candidate['evidence'][0]['year'], 2021)
        self.assertIsNone(candidate['evidence'][0]['effective_date'])

    def test_duplicate_name_returns_candidates(self):
        r = self.index.match('朝阳区')
        self.assertEqual(r['status'], 'ambiguous')
        self.assertEqual(r['candidate_total'], 2)
        self.assertTrue(all(c['suggested_address'] is None for c in r['candidates']))

    def test_scope_resolves_duplicate(self):
        r = self.index.match('北京朝阳区')
        self.assertEqual(r['candidate_total'], 1)
        self.assertEqual(r['candidates'][0]['code'], '110105000000')

    def test_unknown_address(self):
        self.assertEqual(self.index.match('不存在省不存在县')['status'], 'unmatched')

    def test_missing_town_is_partial(self):
        r = self.index.match('河南省洛阳市偃师区董村')
        self.assertEqual(r['status'], 'partial')
        self.assertIsNone(r['candidates'][0]['suggested_address'])

    def test_road_is_not_town(self):
        r = self.index.match('河南省洛阳市偃师区002乡道')
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(r['candidates'][0]['matched_level'], 3)

    def test_conflicting_province_city_requires_review(self):
        r = self.index.match('吉林省洛阳市偃师区大口镇')
        self.assertEqual(r['status'], 'needs_review')
        self.assertIsNone(r['candidates'][0]['suggested_address'])

    def test_merge_requires_review_even_with_town(self):
        r = self.index.match('重庆市江北区某某街道某号')
        self.assertEqual(r['status'], 'needs_review')
        self.assertFalse(r['candidates'][0]['automatic_conversion'])

    def test_snapshot_difference_never_creates_event(self):
        h = self.index.history('410307110')
        self.assertEqual(len(h['snapshots']), 2)
        self.assertFalse(h['snapshot_differences_are_events'])
        self.assertEqual(h['events'], [])

    def test_old_snapshot_name_without_evidence_requires_review(self):
        r = self.index.match('河南省洛阳市偃师区另一个镇')
        self.assertEqual(r['status'], 'needs_review')
        self.assertTrue(r['historical_unresolved'])
        self.assertIsNone(r['candidates'][0]['suggested_address'])

    def test_history_finds_predecessor(self):
        h = self.index.history('410307')
        self.assertEqual(h['events'][0]['old_code'], '410381000000')
        self.assertFalse(h['history_complete'])

    def test_search_old_name(self):
        self.assertEqual(self.index.search('偃师市')['historical'][0]['current_candidates'][0]['name'], '偃师区')

    def test_reject_invalid_address_and_code(self):
        for value in [None, '', 'a', 'x'*1001]:
            with self.assertRaises(ValueError): self.index.match(value)
        with self.assertRaises(ValueError): self.index.history('../data')
        with self.assertRaises(KeyError): self.index.history('999999')

    def test_data_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            make_data(directory)
            Path(directory, 'regions.json').write_text('{}')
            with self.assertRaises(ValueError): RegionIndex(directory)


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        make_data(self.temp.name)
        self.payload = json.loads(Path(self.temp.name, 'regions.json').read_text())

    def index(self):
        write_data(self.temp.name, self.payload)
        return RegionIndex(self.temp.name)

    def test_only_target_year_active_names_in_code_order(self):
        self.payload['records'].extend([
            dict(code='410381000000', name='偃师市', level=3, parent_code='410300000000', year=2023, status='active'),
            dict(code='410399000000', name='已撤销县', level=3, parent_code='410300000000', year=2026, status='inactive'),
            dict(code='410307110001', name='村级不进入目录', level=5, parent_code='410307110000', year=2026, status='active')])
        self.payload['records'].reverse()
        index = self.index()
        result = index.division_tree()
        self.assertEqual([p['province'] for p in result['data']], ['北京市', '吉林省', '河南省', '重庆市'])
        luoyang = result['data'][2]['cities'][0]
        self.assertEqual(luoyang, {'city': '洛阳市', 'districts': ['偃师区'],
                                   'towns': {'偃师区': ['大口镇']}, 'direct_towns': []})
        rendered = json.dumps(result, ensure_ascii=False)
        for old_name in ('偃师市', '另一个镇', '江北区', '已撤销县', '村级不进入目录'):
            self.assertNotIn(old_name, rendered)
        self.assertEqual(result['edition'], '2026-10')
        self.assertEqual(result['target_year'], 2026)
        self.assertEqual(result['data_sha256'], index.digest)
        self.assertIs(result['current_only'], True)
        self.assertEqual(result['excluded_incomplete_paths'], 0)

    def test_prefecture_direct_town_does_not_invent_a_county(self):
        self.payload['records'].append(dict(code='410300110000', name='直属镇', level=4,
            parent_code='410300000000', year=2026, status='active'))
        result = self.index().division_tree()
        self.assertEqual(result['excluded_incomplete_paths'], 0)
        luoyang = next(p for p in result['data'] if p['province'] == '河南省')['cities'][0]
        self.assertEqual(luoyang['districts'], ['偃师区'])
        self.assertEqual(luoyang['direct_towns'], ['直属镇'])
        self.assertNotIn('直属镇', luoyang['towns'])

    def test_municipal_group_with_a_real_county_keeps_the_county_level(self):
        self.payload['records'].append(dict(code='110105001000', name='建外街道', level=4,
            parent_code='110105000000', year=2026, status='active'))
        index = self.index()
        city = next(p for p in index.division_tree()['data'] if p['province'] == '北京市')['cities'][0]
        self.assertEqual(city['city'], '市辖区')
        self.assertEqual(city['districts'], ['朝阳区'])
        self.assertEqual(city['towns'], {'朝阳区': ['建外街道']})
        self.assertEqual(city['direct_towns'], [])
        self.assertEqual([node['level'] for node in index.paths['110105001000']], [1, 2, 3, 4])

    def test_exact_current_path_beats_cross_boundary_name_fragment(self):
        for code, name, level, parent in [
                ('440000000000', '广东省', 1, None), ('442000000000', '中山市', 2, '440000000000'),
                ('442000005000', '南区街道', 4, '442000000000'),
                ('370000000000', '山东省', 1, None), ('370200000000', '青岛市', 2, '370000000000'),
                ('370202000000', '市南区', 3, '370200000000')]:
            self.payload['records'].append(dict(code=code, name=name, level=level,
                parent_code=parent, year=2026, status='active'))
        self.payload['provinces'].extend([{'province': '44'}, {'province': '37'}])
        index = self.index()
        address = '广东省中山市南区街道'
        self.assertIn((5, 8, '市南区'), index.occurrences(address, False))
        result = index.match(address)
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['candidate_total'], 1)
        candidate = result['candidates'][0]
        self.assertEqual(candidate['code'], '442000005000')
        self.assertEqual([node['level'] for node in candidate['path']], [1, 2, 4])
        self.assertEqual(candidate['matched_level'], 4)
        self.assertFalse(candidate['automatic_conversion'])
        for conflict in ('山东省中山市南区街道', '广东省中山市不存在区南区街道'):
            self.assertNotIn(index.match(conflict)['status'], ('matched', 'historical'))

    def test_exact_path_must_still_be_unique(self):
        for code in ('410300110000', '410300111000'):
            self.payload['records'].append(dict(code=code, name='直属镇', level=4,
                parent_code='410300000000', year=2026, status='active'))
        result = self.index().match('河南省洛阳市直属镇')
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual(result['candidate_total'], 2)

    def test_direct_town_and_county_with_same_name_keep_distinct_kinds(self):
        for code in ('410300110000', '410300111000'):
            self.payload['records'].append(dict(code=code, name='偃师区', level=4,
                parent_code='410300000000', year=2026, status='active'))
        tree = self.index().division_tree()['data']
        luoyang = next(p for p in tree if p['province'] == '河南省')['cities'][0]
        self.assertEqual(luoyang['districts'], ['偃师区'])
        self.assertEqual(luoyang['direct_towns'], ['偃师区'])
        self.assertEqual(luoyang['towns'], {'偃师区': ['大口镇']})

    def test_duplicate_names_merge_only_within_the_same_parent(self):
        self.payload['records'].extend([
            dict(code='410308000000', name='偃师区', level=3, parent_code='410300000000', year=2026, status='active'),
            dict(code='410308110000', name='大口镇', level=4, parent_code='410308000000', year=2026, status='active'),
            dict(code='410308111000', name='新镇', level=4, parent_code='410308000000', year=2026, status='active'),
            dict(code='410400000000', name='洛阳市', level=2, parent_code='410000000000', year=2026, status='active')])
        data = self.index().division_tree()['data']
        henan = next(p for p in data if p['province'] == '河南省')
        self.assertEqual(henan['cities'], [{'city': '洛阳市', 'districts': ['偃师区'],
                                          'towns': {'偃师区': ['大口镇', '新镇']}, 'direct_towns': []}])
        self.assertEqual(sum(city['districts'].count('朝阳区') for p in data for city in p['cities']), 2)

    def test_incomplete_or_wrong_level_parent_chain_is_rejected(self):
        for parent in ('419900000000', '410000000000', '220100000000'):
            with self.subTest(parent=parent):
                self.payload['records'][-1] = dict(code='410399000000', name='坏父链县', level=3,
                    parent_code=parent, year=2026, status='active')
                with self.assertRaises(CurrentTreeUnavailable):
                    self.index().division_tree()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        make_data(cls.temp.name)
        cls.server = BoundedServer(('127.0.0.1', 0), RegionIndex(cls.temp.name))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        if isinstance(body, str):
            body = body.encode('utf-8')
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, response.read())
        connection.close()
        return result

    def test_health_docs_and_schema(self):
        for path in ['/health', '/docs', '/openapi.json', '/api/coverage']:
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_current_directory_and_openapi_contract(self):
        status, body = self.request('GET', '/api/divisions/tree')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.server.index.division_tree())
        schema = json.loads(self.request('GET', '/openapi.json')[1])
        endpoint = schema['paths']['/api/divisions/tree']['get']
        self.assertIn('503', endpoint['responses'])
        result_schema = endpoint['responses']['200']['content']['application/json']['schema']
        self.assertEqual(result_schema['properties']['current_only'], {'const': True})
        cities = result_schema['properties']['data']['items']['properties']['cities']['items']
        self.assertIn('direct_towns', cities['properties'])
        self.assertEqual(self.request('GET', '/api/divisions/tree?limit=50')[0], 400)
        self.assertEqual(self.request('GET', '/api/divisions/tree?year=2023')[0], 400)

    def test_broken_directory_returns_unavailable_without_fallback(self):
        original = self.server.index.paths['410307000000']
        try:
            self.server.index.paths['410307000000'] = original[1:]
            status, body = self.request('GET', '/api/divisions/tree')
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(body), {'error': 'Current administrative directory unavailable'})
        finally:
            self.server.index.paths['410307000000'] = original

    def test_direct_town_http_keeps_level_four_and_distinct_directory_list(self):
        original = self.server.index
        try:
            with tempfile.TemporaryDirectory() as directory:
                make_data(directory)
                payload = json.loads(Path(directory, 'regions.json').read_text())
                payload['records'].append(dict(code='410300110000', name='直属镇', level=4,
                    parent_code='410300000000', year=2026, status='active'))
                write_data(directory, payload)
                self.server.index = RegionIndex(directory)
                status, body = self.request('GET', '/api/divisions/tree')
                self.assertEqual(status, 200)
                city = next(p for p in json.loads(body)['data'] if p['province'] == '河南省')['cities'][0]
                self.assertEqual(city['direct_towns'], ['直属镇'])
                self.assertNotIn('直属镇', city['districts'])
                status, body = self.request('POST', '/api/addresses/match',
                    json.dumps({'address': '河南省洛阳市直属镇'}), {'Content-Type': 'application/json'})
                self.assertEqual(status, 200)
                candidate = json.loads(body)['candidates'][0]
                self.assertEqual(candidate['matched_level'], 4)
                self.assertEqual([node['level'] for node in candidate['path']], [1, 2, 4])
        finally:
            self.server.index = original

    def test_batch_preserves_input_order(self):
        values = ['朝阳区', '河南省洛阳市偃师市大口镇董村', '不存在省不存在县']
        status, data = self.request('POST', '/api/addresses/match-batch',
                                    json.dumps({'addresses': values}), {'Content-Type':'application/json'})
        result = json.loads(data)
        self.assertEqual(status, 200)
        self.assertEqual([r['input'] for r in result['results']], values)
        self.assertEqual([r['status'] for r in result['results']], ['ambiguous','historical','unmatched'])

    def test_invalid_batch_rejected_atomically(self):
        for values in [[], ['有效地址'] * 101, ['朝阳区', None]]:
            self.assertEqual(self.request('POST','/api/addresses/match-batch',
                             json.dumps({'addresses':values}), {'Content-Type':'application/json'})[0],400)

    def test_json_and_size_validation(self):
        self.assertEqual(self.request('POST','/api/addresses/match','{}')[0],415)
        for body in ['[]', '{', '{"address":null}', '{"address":"朝阳区","extra":1}']:
            self.assertEqual(self.request('POST','/api/addresses/match',body,
                             {'Content-Type':'application/json'})[0],400)
        self.assertEqual(self.request('POST','/api/addresses/match','x'*262145,
                         {'Content-Type':'application/json'})[0],413)

    def test_not_found_and_bad_queries(self):
        self.assertEqual(self.request('GET','/api/divisions/999999/history')[0],404)
        self.assertEqual(self.request('GET','/api/divisions/bad/history')[0],400)
        self.assertEqual(self.request('GET','/api/divisions/search?q=ab&limit=100')[0],400)
        self.assertEqual(self.request('GET','/api/divisions/search?q=ab&q=cd')[0],400)
        self.assertEqual(self.request('GET','/unknown')[0],404)


@unittest.skipUnless(os.getenv('REGION_TEST_DATA'), 'Set REGION_TEST_DATA for release-data tests')
class ReleaseTests(unittest.TestCase):
    def test_complete_current_tree_and_fuzhou_counties(self):
        index = RegionIndex(os.environ['REGION_TEST_DATA'])
        result = index.division_tree()
        self.assertEqual(len(result['data']), 31)
        self.assertEqual(result['edition'], index.data['edition'])
        self.assertEqual(result['target_year'], index.year)
        self.assertEqual(result['data_sha256'], index.digest)
        self.assertIs(result['current_only'], True)
        actual = set()
        for province in result['data']:
            actual.add((province['province'],))
            for city in province['cities']:
                parent = (province['province'], city['city'])
                actual.add(parent)
                self.assertEqual(set(city['districts']), set(city['towns']))
                for district in city['districts']:
                    actual.add((*parent, district))
                    for town in city['towns'][district]:
                        actual.add((*parent, district, town))
                for town in city['direct_towns']:
                    actual.add((*parent, '', town))
        expected = set()
        for code, row in index.current.items():
            slots = [''] * row['level']
            for node in index.paths[code]:
                slots[node['level'] - 1] = node['name']
            expected.add(tuple(slots))
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 41989)
        direct_towns = [code for code in index.current
                        if [n['level'] for n in index.paths[code]] == [1, 2, 4]]
        self.assertEqual(result['excluded_incomplete_paths'], 0)
        self.assertEqual(len(direct_towns), 102)
        self.assertEqual(sum(len(c['direct_towns']) for p in result['data'] for c in p['cities']), 102)
        fujian = next(p for p in result['data'] if p['province'] == '福建省')
        fuzhou = next(c for c in fujian['cities'] if c['city'] == '福州市')
        catalog = [r['name'] for code, r in sorted(index.current.items())
                   if r['level'] == 3 and r['parent_code'] == '350100000000']
        self.assertEqual(fuzhou['districts'], list(dict.fromkeys(catalog)))
        self.assertEqual(len(fuzhou['districts']), 13)
        self.assertIn('长乐区', fuzhou['districts'])
        self.assertNotIn('长乐市', fuzhou['districts'])

    def test_all_prefecture_direct_towns_match_at_their_real_level(self):
        index = RegionIndex(os.environ['REGION_TEST_DATA'])
        direct = {code: path for code, path in index.paths.items()
                  if [node['level'] for node in path] == [1, 2, 4]}
        self.assertEqual(len(direct), 102)
        for code, path in direct.items():
            with self.subTest(code=code):
                result = index.match(''.join(node['name'] for node in path))
                self.assertEqual(result['status'], 'matched')
                self.assertEqual(result['candidate_total'], 1)
                candidate = result['candidates'][0]
                self.assertEqual(candidate['code'], code)
                self.assertEqual(candidate['matched_level'], 4)
                self.assertEqual([node['level'] for node in candidate['path']], [1, 2, 4])

    def test_real_station_samples_and_old_address(self):
        index = RegionIndex(os.environ['REGION_TEST_DATA'])
        self.assertEqual(len(index.current),41989)
        self.assertEqual(len(index.provinces),31)
        samples = [('山东省滨州市沾化区大高镇桑家村','matched'),
                   ('安徽省六安市金安区黄泥店村青松组','partial'),
                   ('湖北省恩施土家族苗族自治州利川市建南镇建兴村','matched'),
                   ('安徽省淮南市大通区002乡道靠近曹家湖','partial'),
                   ('河南省洛阳市偃师区大口镇董村','matched'),
                   ('河南省洛阳市偃师市大口镇董村','historical'),
                   ('陕西省宝鸡市凤翔县南指挥镇某村','historical'),
                   ('不存在省不存在县','unmatched')]
        for address,status in samples:
            with self.subTest(address=address): self.assertEqual(index.match(address)['status'],status)
        history = index.history('371603104')
        self.assertEqual(history['events'],[])
        self.assertEqual({r['name'] for r in history['snapshots']},{'泊头镇','大高镇'})


if __name__ == '__main__':
    unittest.main()
