"""Management names are not legal division nodes, and never widen responsibility."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from region_check import RegionIndex
from managed_areas import build_catalog
from build_data import augment_release
from test_region_check import make_data, write_data


CATALOG = Path(__file__).with_name('managed_areas.json')


def managed_data(directory):
    make_data(directory)
    payload = json.loads(Path(directory, 'regions.json').read_text())
    rows = payload['records']
    def row(code, name, level, parent=None, year=2026):
        rows.append(dict(code=code, name=name, level=level, parent_code=parent,
                         year=year, status='active'))
    row('320000000000', '江苏省', 1)
    row('321000000000', '扬州市', 2, '320000000000')
    row('321084000000', '高邮市', 3, '321000000000')
    row('321084001000', '高邮街道', 4, '321084000000')
    row('321084002000', '马棚街道', 4, '321084000000')
    row('321084406000', '经济开发区（马棚街道）', 4, '321084000000', 2023)
    row('520000000000', '贵州省', 1)
    row('520300000000', '遵义市', 2, '520000000000')
    row('520302000000', '红花岗区', 3, '520300000000')
    row('520304000000', '播州区', 3, '520300000000')
    row('520304001000', '南白街道', 4, '520304000000')
    row('520302009000', '忠庄街道', 4, '520302000000')
    for code, name in [('520302013000','新蒲街道'),('520302014000','新中街道'),
                       ('520302015000','礼仪街道'),('520302109000','新舟镇'),
                       ('520302110000','永乐镇'),('520302111000','喇叭镇'),
                       ('520302112000','虾子镇'),('520302113000','三渡镇')]:
        row(code, name, 4, '520302000000')
    row('410371000000', '示例经济技术开发区', 3, '410300000000', 2023)
    row('410000000000', '河南省', 1, year=2023)
    row('410300000000', '洛阳市', 2, '410000000000', 2023)
    payload['provinces'] += [{'province': n, 'name': n, 'as_of': None} for n in ['32','52']]
    curated = json.loads(CATALOG.read_text())
    curated['areas'] = curated['areas'][:2]
    payload['managed_areas'] = build_catalog(rows, 2026, curated)
    write_data(directory, payload)
    return payload


class ManagedAreaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.payload = managed_data(self.temp.name)
        self.index = RegionIndex(self.temp.name)

    def test_gaoyou_development_name_maps_to_actual_street(self):
        for name in ['经济开发区', '经济开发区（马棚街道）', '高邮经济开发区']:
            result = self.index.match('江苏省扬州市高邮市' + name)
            self.assertEqual(result['status'], 'managed')
            area = result['managed_areas']['matches'][0]
            self.assertEqual([p[-1]['name'] for p in area['scope_paths']], ['马棚街道'])
            self.assertEqual([n['level'] for n in area['scope_paths'][0]], [1,2,3,4])

    def test_pingdingshan_preserves_two_county_parent_chains(self):
        payload = copy.deepcopy(self.payload)
        for code, name, level, parent in [
                ('410400000000','平顶山市',2,'410000000000'),
                ('410403000000','卫东区',3,'410400000000'),
                ('410422000000','叶县',3,'410400000000'),
                ('410403009000','皇台街道',4,'410403000000'),
                ('410422104000','遵化店镇',4,'410422000000'),
                ('410403001000','东安路街道',4,'410403000000')]:
            payload['records'].append(dict(code=code,name=name,level=level,
                parent_code=parent,year=2026,status='active'))
        area = next(a for a in json.loads(CATALOG.read_text())['areas']
                    if a['id']=='henan-pingdingshan-high-tech-area')
        payload['managed_areas']['areas'].append(area)
        with tempfile.TemporaryDirectory() as directory:
            write_data(directory,payload)
            index=RegionIndex(directory)
            result=index.match('河南省平顶山市高新区')
            self.assertEqual(result['status'],'managed')
            paths=result['managed_areas']['matches'][0]['scope_paths']
            self.assertEqual({tuple(n['name'] for n in p[-2:]) for p in paths},
                             {('卫东区','皇台街道'),('叶县','遵化店镇')})
            self.assertNotEqual(index.match('河南省平顶山市高新区东安路街道')['status'],'managed')

    def test_xinpu_is_eight_towns_and_not_whole_honghuagang(self):
        result = self.index.match('贵州省遵义市新蒲新区')
        area = result['managed_areas']['matches'][0]
        self.assertEqual(result['status'], 'managed')
        self.assertEqual(len(area['scope_paths']), 8)
        self.assertTrue(all(p[-2]['name']=='红花岗区' for p in area['scope_paths']))
        self.assertNotIn('忠庄街道', [p[-1]['name'] for p in area['scope_paths']])
        self.assertTrue(all(p[-1]['level']==4 for p in area['scope_paths']))

    def test_explicit_member_can_narrow_but_unknown_suffix_cannot_disappear(self):
        area = self.index.match('贵州省遵义市新蒲新区新蒲街道')['managed_areas']
        self.assertEqual(area['status'], 'verified')
        self.assertEqual(len(area['matches'][0]['scope_paths']), 1)
        for suffix in ['忠庄街道', '不存在镇', '村名未核验']:
            area = self.index.match('贵州省遵义市新蒲新区'+suffix)['managed_areas']
            self.assertEqual(area['status'], 'partial')
            self.assertFalse(area['matches'][0]['scope_paths'])
            self.assertEqual(area['matches'][0]['unparsed_suffix'], suffix)

    def test_conflicting_parent_and_unqualified_generic_do_not_match(self):
        for address in ['广东省遵义市新蒲新区', '河南省扬州市高邮市经济开发区', '经济开发区']:
            self.assertNotIn('managed_areas', self.index.match(address))

    def test_admin_tree_and_ordinary_town_are_unchanged(self):
        payload = copy.deepcopy(self.payload)
        payload.pop('managed_areas')
        with tempfile.TemporaryDirectory() as d:
            write_data(d, payload)
            plain = RegionIndex(d)
        self.assertEqual(self.index.division_tree()['data'], plain.division_tree()['data'])
        self.assertEqual(self.index.match('江苏省扬州市高邮市高邮街道')['candidates'],
                         plain.match('江苏省扬州市高邮市高邮街道')['candidates'])
        self.assertEqual(self.index.match('重庆市市辖区两江新区某某街道')['status'], 'matched')

    def test_old_statistical_area_is_system_mapping_gap_not_verified_scope(self):
        result = self.index.match('河南省洛阳市示例经济技术开发区')['managed_areas']
        self.assertEqual(result['status'], 'mapping_required')
        self.assertEqual(result['matches'][0]['scope_paths'], [])
        self.assertTrue(self.index.search('经济开发区')['managed_areas'])

    def test_lujiang_park_catalog_merges_old_name_without_granting_whole_towns(self):
        payload = copy.deepcopy(self.payload)
        payload['provinces'].append({'province':'34','name':'安徽省','as_of':None})
        for code,name,level,parent,year in [
            ('340000000000','安徽省',1,None,2026),
            ('340100000000','合肥市',2,'340000000000',2026),
            ('340124000000','庐江县',3,'340100000000',2026),
            ('340124104000','郭河镇',4,'340124000000',2026),
            ('340124107000','同大镇',4,'340124000000',2026),
            ('340124404000','台创园管委会',4,'340124000000',2023)]:
            payload['records'].append(dict(code=code,name=name,level=level,
                parent_code=parent,year=year,status='active'))
        park = next(a for a in json.loads(CATALOG.read_text())['areas']
                    if a['id']=='anhui-lujiang-taiwan-farmers-startup-area')
        payload['managed_areas'] = build_catalog(payload['records'],2026,
            {'edition':'2026-10-26','areas':[park]})
        self.assertFalse(any(a['id']=='nbs-2023-340124404000'
                             for a in payload['managed_areas']['areas']))
        write_data(self.temp.name,payload)
        index = RegionIndex(self.temp.name)
        for name in ('台创园','台创园管委会','庐江台湾农民创业园'):
            result=index.match('安徽省合肥市庐江县'+name)['managed_areas']
            self.assertEqual(result['candidate_total'],1)
            self.assertEqual(result['status'],'mapping_required')
            self.assertEqual(result['matches'][0]['scope_paths'],[])
            self.assertIn('10个村',result['matches'][0]['note'])
        self.assertNotIn('台创园',str(index.division_tree()['data']))

    def test_duplicate_proper_names_remain_ambiguous_without_parent(self):
        area = copy.deepcopy(self.payload['managed_areas']['areas'][1])
        area.update(id='same-name-other-city',parent_code='410300000000',scope_codes=['410307110000'])
        self.payload['managed_areas']['areas'].append(area)
        write_data(self.temp.name,self.payload)
        index = RegionIndex(self.temp.name)
        self.assertEqual(index.match('新蒲新区')['managed_areas']['status'], 'ambiguous')
        self.assertEqual(index.match('贵州省遵义市新蒲新区')['managed_areas']['candidate_total'], 1)

    def test_union_may_cross_counties_but_not_escape_its_city(self):
        area = copy.deepcopy(self.payload['managed_areas']['areas'][1])
        area.update(id='cross-county-test',name='跨区示范区',aliases=[],
                    scope_codes=['520302013000','520304001000'])
        self.payload['managed_areas']['areas'].append(area)
        write_data(self.temp.name,self.payload)
        index = RegionIndex(self.temp.name)
        area=index.match('贵州省遵义市跨区示范区')['managed_areas']['matches'][0]
        self.assertEqual({p[-2]['name'] for p in area['scope_paths']},{'红花岗区','播州区'})
        self.payload['managed_areas']['areas'][-1]['scope_codes'].append('410307110000')
        write_data(self.temp.name,self.payload)
        with self.assertRaises(ValueError):RegionIndex(self.temp.name)

    def test_missing_member_and_unsupported_source_fail_closed(self):
        for key,value in [('scope_codes',['999999999999']),('sources',[{'url':'file:///tmp/fake'}])]:
            payload=copy.deepcopy(self.payload)
            payload['managed_areas']['areas'][0][key]=value
            write_data(self.temp.name,payload)
            with self.assertRaises(ValueError):RegionIndex(self.temp.name)

    def test_catalog_release_preserves_all_administrative_records_and_checks_base_hash(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as output_parent:
            catalog=Path(repo,'apps/region-check/managed_areas.json')
            catalog.parent.mkdir(parents=True)
            curated=json.loads(CATALOG.read_text());curated['areas']=curated['areas'][:2]
            catalog.write_text(json.dumps(curated,ensure_ascii=False))
            output=Path(output_parent,'release')
            augment_release(self.temp.name,output,repo)
            after=json.loads((output/'regions.json').read_text())
            self.assertEqual(after['records'],self.payload['records'])
            self.assertEqual(after['events'],self.payload['events'])
            self.assertEqual(RegionIndex(output).division_tree()['data'],self.index.division_tree()['data'])
            Path(self.temp.name,'regions.json').write_text('{}')
            with self.assertRaises(ValueError):augment_release(self.temp.name,Path(output_parent,'bad'),repo)

    def test_managed_subdistrict_administered_within_and_three_tier_bridge(self):
        payload = copy.deepcopy(self.payload)
        for code, name, level, parent, year in [
            ('320800000000', '淮安市', 2, '320000000000', 2026),
            ('320803000000', '淮安区', 3, '320800000000', 2026),
            ('320871000000', '淮安经济技术开发区', 3, '320800000000', 2023),
            ('320871412000', '高铁商务区办', 4, '320871000000', 2023),
            ('410600000000', '鹤壁市', 2, '410000000000', 2026),
            ('410611000000', '淇滨区', 3, '410600000000', 2026),
        ]:
            payload['records'].append(dict(code=code, name=name, level=level,
                                           parent_code=parent, year=year, status='active'))
        curated = json.loads(CATALOG.read_text())
        selected = [a for a in curated['areas'] if a['id'] in {
            'jiangsu-huaian-edz-gaotie-subdistrict',
            'henan-hebi-economic-development-area',
            'henan-hebi-edz-longgang-subdistrict',
            'henan-hebi-edz-bohailu-subdistrict',
        }]
        payload['managed_areas'] = build_catalog(payload['records'], 2026,
                                                 {'edition': curated['edition'], 'areas': selected})
        with tempfile.TemporaryDirectory() as directory:
            write_data(directory, payload)
            index = RegionIndex(directory)
            res = index.match('江苏省淮安市淮安经济技术开发区高铁新区办事处')
            self.assertEqual(res['status'], 'managed')
            m = res['managed_areas']['matches'][0]
            self.assertEqual(m['id'], 'jiangsu-huaian-edz-gaotie-subdistrict')
            self.assertEqual(m['area_type'], 'managed_subdistrict')
            self.assertEqual(m['relation'], 'administered_within')
            self.assertEqual(m['scope_semantics'], 'legal_container_only')
            self.assertEqual(m['effective_from'], '2019')
            self.assertIsNone(m['effective_to'])
            self.assertEqual(m['verified_at'], '2026-11-27')
            self.assertEqual(m['legacy_codes'], ['320871412000'])
            self.assertEqual(m['standard_bridge']['legal_target_levels'], [3])
            self.assertEqual([n['name'] for n in m['scope_paths'][0]], ['江苏省', '淮安市', '淮安区'])
            # Longest match beats parent dev zone for Hebi subdistricts
            for addr, expected_id in [
                ('河南省鹤壁市鹤壁经济技术开发区龙岗街道', 'henan-hebi-edz-longgang-subdistrict'),
                ('河南省鹤壁市鹤壁经济技术开发区渤海路办事处', 'henan-hebi-edz-bohailu-subdistrict'),
                ('河南省鹤壁市鹤壁经济技术开发区', 'henan-hebi-economic-development-area'),
            ]:
                r2 = index.match(addr)
                self.assertEqual(r2['status'], 'managed')
                self.assertEqual(r2['managed_areas']['matches'][0]['id'], expected_id)
                self.assertEqual([n['name'] for n in r2['managed_areas']['matches'][0]['scope_paths'][0]],
                                 ['河南省', '鹤壁市', '淇滨区'])

    def test_invalid_area_type_or_temporal_fields_fail_closed(self):
        for key, value in [
            ('area_type', 'unknown_kind'),
            ('effective_from', '2026/11/27'),
            ('verified_at', 'not-a-date'),
            ('legacy_codes', ['12345']),
        ]:
            payload = copy.deepcopy(self.payload)
            payload['managed_areas']['areas'][0][key] = value
            write_data(self.temp.name, payload)
            with self.assertRaises(ValueError):
                RegionIndex(self.temp.name)


if __name__ == '__main__':
    unittest.main()
