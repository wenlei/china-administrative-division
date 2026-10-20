"""Offline regression tests; run: python3 -m unittest discover -s scripts -p 'test_official_update.py'."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('official_update',Path(__file__).with_name('build-official-update.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class OfficialUpdateTests(unittest.TestCase):
    def test_merged_upper_cells_and_reordered_codes(self):
        rows=[['江苏省 320000（1市）','南京市 320100','秦淮区 320104','中华门街道',320104006.0],
              ['','','','五老村街道',320104009.0]]
        data=module.parse_table(rows,'32','江苏省',2)
        self.assertEqual(data['320104006']['name'],'中华门街道')
        self.assertEqual(data['320104009']['parent_code'],'320104')
        self.assertEqual(data['320104']['name'],'秦淮区')

    def test_chongqing_rowspan_does_not_rename_county(self):
        rows=[['1','万州区（2街道）','高笋塘街道','500101001'],['2','太白街道','500101002']]
        data=module.parse_table(rows,'50','重庆市',2)
        self.assertEqual(data['500101']['name'],'万州区')

    def test_jilin_names_without_separate_upper_codes(self):
        data=module.parse_table([['1','长春市','南关区','南岭街道','220102001']], '22','吉林省',1)
        self.assertEqual(data['220100']['name'],'长春市')
        self.assertEqual(data['220102']['name'],'南关区')

    def test_conflicting_duplicate_and_partial_source_are_rejected(self):
        rows=[['福建省','350000'],['福州市','350100'],['鼓楼区','350102'],['鼓东街道','350102001']]
        with self.assertRaisesRegex(ValueError,'expected 2'):
            module.parse_table(rows,'35','福建省',2)
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):
            module.parse_table(rows+[['别的街道','350102001']],'35','福建省',1)

    def test_source_rare_character_spelling_is_not_removed(self):
        self.assertEqual(module.name_only('（门+合）山镇'),'（门+合）山镇')
        self.assertEqual(module.name_only('江西省（乡级1581个）'),'江西省')

    def test_patch_changes_target_names_and_keeps_deprecated_history(self):
        baseline=[dict(code='350000000000',name='福建省',level=1,parent_code=None),
            dict(code='350100000000',name='福州市',level=2,parent_code='350000000000'),
            dict(code='350102000000',name='鼓楼区',level=3,parent_code='350100000000'),
            dict(code='350102001000',name='旧码名称',level=4,parent_code='350102000000'),
            dict(code='350102400000',name='统计用农场',level=4,parent_code='350102000000')]
        data=module.parse_table([['福建省','350000'],['福州市','350100'],['鼓楼区','350102'],['鼓东街道','350102001']],'35','福建省',1)
        patch=module.build_patch(dict(province='35',url='https://example.gov.cn/source',as_of='2026-06-30',sha256='a'*64,expected_towns=1),data,baseline)
        self.assertIn(dict(op='update',code='350102001000',name='鼓东街道'),patch['operations'])
        self.assertTrue(any(o.get('status')=='deprecated' and o['code']=='350102400000' for o in patch['operations']))
        self.assertEqual(baseline[3]['name'],'旧码名称')
        self.assertEqual(patch['meta']['apply_after'],'2023-baseline')

if __name__=='__main__':unittest.main()
