"""Regression and real HTTP tests; full-data tests use REGION_TEST_DATA."""
import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from region_check import RegionIndex
from server import BoundedServer


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
    data = json.dumps(payload, ensure_ascii=False).encode()
    Path(directory, 'regions.json').write_bytes(data)
    Path(directory, 'manifest.json').write_text(json.dumps({'sha256': hashlib.sha256(data).hexdigest()}))


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
