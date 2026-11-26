"""Tests for verified 2014-2020 official county succession patches."""
import json
import tempfile
import unittest
from pathlib import Path

from build_data import ROOT, augment_release, extract_events
from region_check import RegionIndex
from test_region_check import write_data


def make_historical_fixture(directory):
    records = []

    def row(code, name, level, parent=None, year=2026):
        records.append(dict(
            code=code.ljust(12, '0'),
            name=name,
            level=level,
            parent_code=parent.ljust(12, '0') if parent else None,
            year=year,
            status='active',
        ))

    provinces = [
        ('12', '天津市'),
        ('34', '安徽省'),
        ('35', '福建省'),
        ('37', '山东省'),
        ('41', '河南省'),
        ('43', '湖南省'),
        ('45', '广西壮族自治区'),
        ('50', '重庆市'),
        ('52', '贵州省'),
        ('53', '云南省'),
    ]
    for code, name in provinces:
        row(code + '0000', name, 1)

    cities = [
        ('120100', '市辖区', '120000'),
        ('340200', '芜湖市', '340000'),
        ('340800', '安庆市', '340000'),
        ('350700', '南平市', '350000'),
        ('371600', '滨州市', '370000'),
        ('410700', '新乡市', '410000'),
        ('411000', '许昌市', '410000'),
        ('419000', '省直辖县级行政区划', '410000'),
        ('430700', '常德市', '430000'),
        ('450300', '桂林市', '450000'),
        ('451000', '百色市', '450000'),
        ('500100', '市辖区', '500000'),
        ('500200', '县', '500000'),
        ('520200', '六盘水市', '520000'),
        ('530100', '昆明市', '530000'),
        ('533300', '怒江傈僳族自治州', '530000'),
    ]
    for code, name, parent in cities:
        row(code, name, 2, parent)

    districts = [
        ('120114', '武清区', '120100'),
        ('340209', '弋江区', '340200'),
        ('340210', '湾沚区', '340200'),
        ('340212', '繁昌区', '340200'),
        ('340281', '无为市', '340200'),
        ('340882', '潜山市', '340800'),
        ('350703', '建阳区', '350700'),
        ('371681', '邹平市', '371600'),
        ('410783', '长垣市', '410700'),
        ('411003', '建安区', '411000'),
        ('419001', '济源市', '419000'),
        ('430781', '津市市', '430700'),
        ('450381', '荔浦市', '450300'),
        ('451082', '平果市', '451000'),
        ('500101', '万州区', '500100'),
        ('500236', '奉节县', '500200'),
        ('520201', '钟山区', '520200'),
        ('520204', '水城区', '520200'),
        ('520281', '盘州市', '520200'),
        ('530115', '晋宁区', '530100'),
        ('533301', '泸水市', '533300'),
    ]
    for code, name, parent in districts:
        row(code, name, 3, parent)

    towns = [
        ('450381100', '荔城镇', '450381'),
        ('451082100', '马头镇', '451082'),
        ('340281113', '赫店镇', '340281'),
        ('340210100', '湾沚镇', '340210'),
        ('520204100', '阿戛镇', '520204'),
        ('340209001', '中南街道', '340209'),
    ]
    for code, name, parent in towns:
        row(code, name, 4, parent)

    events = extract_events(records, ROOT)
    payload = {
        'edition': '2026-10',
        'target_year': 2026,
        'snapshot_years': [2023, 2026],
        'provinces': [{'province': c, 'name': n, 'as_of': None} for c, n in provinces],
        'records': records,
        'events': events,
        'limitations': ['Historical coverage incomplete'],
    }
    write_data(directory, payload)
    return payload


class HistoricalEventPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.payload = make_historical_fixture(cls.temp.name)
        cls.index = RegionIndex(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_one_to_one_county_events_are_safe_and_convert_cleanly(self):
        expected = [
            ('广西壮族自治区桂林市荔浦县', ['广西壮族自治区', '桂林市', '荔浦市'], 'partial'),
            ('广西壮族自治区桂林市荔浦县荔城镇', ['广西壮族自治区', '桂林市', '荔浦市', '荔城镇'], 'historical'),
            ('广西壮族自治区百色市平果县', ['广西壮族自治区', '百色市', '平果市'], 'partial'),
            ('广西壮族自治区百色市平果县马头镇', ['广西壮族自治区', '百色市', '平果市', '马头镇'], 'historical'),
            ('安徽省芜湖市无为县', ['安徽省', '芜湖市', '无为市'], 'partial'),
            ('安徽省芜湖市无为县赫店镇', ['安徽省', '芜湖市', '无为市', '赫店镇'], 'historical'),
            ('安徽省安庆市潜山县', ['安徽省', '安庆市', '潜山市'], 'partial'),
            ('山东省滨州市邹平县', ['山东省', '滨州市', '邹平市'], 'partial'),
            ('安徽省芜湖市繁昌县', ['安徽省', '芜湖市', '繁昌区'], 'partial'),
            ('安徽省芜湖市芜湖县', ['安徽省', '芜湖市', '湾沚区'], 'partial'),
            ('安徽省芜湖市芜湖县湾沚镇', ['安徽省', '芜湖市', '湾沚区', '湾沚镇'], 'historical'),
            ('贵州省六盘水市盘县', ['贵州省', '六盘水市', '盘州市'], 'partial'),
            ('云南省怒江傈僳族自治州泸水县', ['云南省', '怒江傈僳族自治州', '泸水市'], 'partial'),
            ('福建省南平市建阳市', ['福建省', '南平市', '建阳区'], 'partial'),
            ('云南省昆明市晋宁县', ['云南省', '昆明市', '晋宁区'], 'partial'),
            ('河南省许昌市许昌县', ['河南省', '许昌市', '建安区'], 'partial'),
            ('河南省新乡市长垣县', ['河南省', '新乡市', '长垣市'], 'partial'),
        ]
        for address, path, status in expected:
            with self.subTest(address=address):
                res = self.index.match(address)
                self.assertEqual(res['status'], status)
                self.assertEqual(res['candidate_total'], 1)
                cand = res['candidates'][0]
                self.assertEqual(cand['match_method'], 'official_event')
                self.assertEqual(cand['unparsed_suffix'], '')
                self.assertEqual(cand['unmatched_prefix'], '')
                self.assertEqual([n['name'] for n in cand['path']], path)
                self.assertTrue(cand['evidence'])
                self.assertTrue(all(ev['safe_conversion'] is True for ev in cand['evidence']))

    def test_merge_and_partial_split_events_require_review(self):
        for address in (
            '安徽省芜湖市三山区',
            '安徽省芜湖市三山区中南街道',
            '贵州省六盘水市水城县',
            '贵州省六盘水市水城县阿戛镇',
        ):
            with self.subTest(address=address):
                res = self.index.match(address)
                self.assertEqual(res['status'], 'needs_review')
                self.assertFalse(res['candidates'][0]['automatic_conversion'])
                self.assertTrue(any(ev['safe_conversion'] is False for ev in res['candidates'][0]['evidence']))

    def test_exact_municipality_level2_and_level3_paths_beat_cross_boundary_fragments(self):
        cases = [
            ('天津市市辖区', ['天津市', '市辖区'], 2),
            ('天津市市辖区武清区', ['天津市', '市辖区', '武清区'], 3),
            ('重庆市市辖区', ['重庆市', '市辖区'], 2),
            ('重庆市县', ['重庆市', '县'], 2),
            ('重庆市县奉节县', ['重庆市', '县', '奉节县'], 3),
        ]
        for address, expected_path, level in cases:
            with self.subTest(address=address):
                res = self.index.match(address)
                self.assertEqual(res['status'], 'partial')
                self.assertEqual(res['candidate_total'], 1)
                cand = res['candidates'][0]
                self.assertEqual(cand['matched_level'], level)
                self.assertEqual(cand['unparsed_suffix'], '')
                self.assertEqual(cand['unmatched_prefix'], '')
                self.assertEqual([n['name'] for n in cand['path']], expected_path)

    def test_augment_release_can_refresh_events_without_altering_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base = tmp_path / 'base'
            out = tmp_path / 'out'
            repo = tmp_path / 'repo'
            base.mkdir()
            (repo / 'apps' / 'region-check').mkdir(parents=True)
            (repo / 'apps' / 'region-check' / 'managed_areas.json').write_text(
                json.dumps({'version': 1, 'edition': '2026-10-26', 'areas': []}))
            (repo / 'patches').symlink_to(ROOT / 'patches')
            payload = dict(self.payload, events=[])
            write_data(base, payload)
            before_records = json.loads((base / 'regions.json').read_text())['records']
            augment_release(base, out, repository=repo, refresh_events=True)
            after = json.loads((out / 'regions.json').read_text())
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(after['records'], before_records)
            self.assertGreaterEqual(len(after['events']), 35)
            self.assertEqual(manifest['event_count'], len(after['events']))
            idx = RegionIndex(out)
            self.assertEqual(idx.match('广西壮族自治区桂林市荔浦县')['candidates'][0]['name'], '荔浦市')

    def test_extra_patch_restores_lanping_official_county_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base = tmp_path / 'base'
            out = tmp_path / 'out'
            repo = tmp_path / 'repo'
            base.mkdir()
            (repo / 'apps' / 'region-check').mkdir(parents=True)
            (repo / 'apps' / 'region-check' / 'managed_areas.json').write_text(
                json.dumps({'version': 1, 'edition': '2026-10-26', 'areas': []}))
            (repo / 'patches').symlink_to(ROOT / 'patches')
            (repo / 'updates').symlink_to(ROOT / 'updates')

            records = list(self.payload['records']) + [
                dict(code='533325000000', name='兰坪白族普米族自治县', level=3,
                     parent_code='533300000000', year=2023, status='active'),
                dict(code='533325000000', name='兰坪普米族白族自治县', level=3,
                     parent_code='533300000000', year=2026, status='active'),
                dict(code='533325101000', name='金顶镇', level=4,
                     parent_code='533325000000', year=2026, status='active'),
            ]
            payload = dict(self.payload, records=records)
            write_data(base, payload)
            # Before correction, official name hits historical snapshot mismatch
            before_idx = RegionIndex(base)
            self.assertEqual(before_idx.match('云南省怒江傈僳族自治州兰坪白族普米族自治县金顶镇')['status'], 'needs_review')
            augment_release(base, out, repository=repo, refresh_events=True, apply_extra_patches=True)
            after_idx = RegionIndex(out)
            res = after_idx.match('云南省怒江傈僳族自治州兰坪白族普米族自治县金顶镇')
            self.assertEqual(res['status'], 'matched')
            self.assertEqual(
                [n['name'] for n in res['candidates'][0]['path']],
                ['云南省', '怒江傈僳族自治州', '兰坪白族普米族自治县', '金顶镇'],
            )


if __name__ == '__main__':
    unittest.main()
