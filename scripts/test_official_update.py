"""Offline regression tests; run: python3 -m unittest discover -s scripts -p 'test_official_update.py'."""
import importlib.util
from pathlib import Path
import unittest
import json
import hashlib
import tempfile

spec=importlib.util.spec_from_file_location('official_update',Path(__file__).with_name('build-official-update.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class OfficialUpdateTests(unittest.TestCase):
    def test_image_review_requires_contiguous_serials_unique_codes_and_all_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'review.json'
            review=dict(pages=2,township_count=2,parents=[],townships=[
                dict(serial=1,page=1,code='650102001',name='甲街道',check='original-image-review'),
                dict(serial=2,page=2,code='650102002',name='乙街道',check='ocr-api-exact')])
            path.write_text(json.dumps(review))
            self.assertEqual(len(module.read_rows(path,'reviewed-images')),2)
            review['townships'][1]['serial']=3
            path.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError,'serial coverage'):
                module.read_rows(path,'reviewed-images')
            review['townships'][1]['serial']=2
            review['townships'][1]['page']=1
            path.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError,'page coverage'):
                module.read_rows(path,'reviewed-images')
            review['townships'][1]['page']=2
            review['townships'][1]['code']='650102001'
            path.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                module.read_rows(path,'reviewed-images')

    def test_source_image_bytes_are_verified_not_only_html_and_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'page.html').write_text('official page')
            (root/'review.json').write_text(json.dumps(dict(pages=1)))
            (root/'001.png').write_bytes(b'archived image bytes')
            sha=lambda file:hashlib.sha256((root/file).read_bytes()).hexdigest()
            (root/'images.json').write_text(json.dumps(dict(images=[dict(page=1,file='001.png',sha256=sha('001.png'))])))
            source=dict(province='65',file='review.json',original_file='page.html',sha256=sha('page.html'),
                        parsed_sha256=sha('review.json'),image_manifest='images.json',image_manifest_sha256=sha('images.json'))
            module.verify_source_files(source,root)
            (root/'001.png').write_bytes(b'changed image')
            with self.assertRaisesRegex(ValueError,'Image checksum mismatch'):
                module.verify_source_files(source,root)

    def test_missing_glyph_restoration_is_explicit_and_rejects_new_spelling(self):
        entries={'140781201':dict(name='宋乡')}
        rules={'140781201':dict(extracted_name='宋乡',name='宋𦙶乡')}
        self.assertEqual(module.restore_source_names(entries,rules)['140781201']['name'],'宋𦙶乡')
        with self.assertRaisesRegex(ValueError,'Unreviewed source name'):
            module.restore_source_names({'140781201':dict(name='另一个名称')},rules)

    def test_code_replacement_supplement_removes_only_target_projection(self):
        spec=importlib.util.spec_from_file_location('verify_update',Path(__file__).with_name('verify-official-update.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        original={'500230111000':dict(name='双路镇',level=4,parent_code='500230000000')}
        ops=[dict(op='add',code='500230003000',name='双路街道',level=4,parent_code='500230000000'),
             dict(op='update',code='500230111000',status='deprecated')]
        projected=verifier.project_supplements(original,ops,'50')
        self.assertEqual(set(projected),{'500230003000'})
        self.assertIn('500230111000',original)
        with self.assertRaisesRegex(ValueError,'withdraws missing'):
            verifier.project_supplements({},ops,'50')

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

    def test_guangxi_merged_names_without_upper_codes(self):
        rows=[['1','广西壮族自治区（1街道）','南宁市（1街道）','兴宁区（1街道）','民生街道',450102001.0],
              ['2','','','','朝阳街道','450102002']]
        data=module.parse_table(rows,'45','广西壮族自治区',2)
        self.assertEqual(data['450100']['name'],'南宁市')
        self.assertEqual(data['450102']['name'],'兴宁区')
        self.assertEqual(data['450102002']['parent_code'],'450102')

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
        town=next(o for o in patch['operations'] if o['code']=='350102001000')
        self.assertEqual(town['name'],'鼓东街道')
        self.assertEqual(town['status'],'active')
        self.assertEqual(town['new_parent'],'350102000000')
        # Unchanged 2023 names still need an explicit restore after older events.
        self.assertTrue(any(o['code']=='350102000000' and o.get('status')=='active' for o in patch['operations']))
        self.assertTrue(any(o.get('status')=='deprecated' and o['code']=='350102400000' for o in patch['operations']))
        self.assertEqual(baseline[3]['name'],'旧码名称')
        self.assertEqual(patch['meta']['apply_after'],'2023-baseline')

    def api_snapshot(self, names=('莞城街道',)):
        def node(code,name,level,children=()):
            return dict(code=code.ljust(12,'0'),name=name,level=level,children=list(children))
        towns=[node('441900001',name,4) for name in names]
        city=node('441900','东莞市',2,towns)
        root=node('440000','广东省',1,[node('441900','东莞市',2)])
        def response(code,data):
            return dict(url='https://dmfw.mca.gov.cn/9095/xzqh/getList?code='+code+'&maxLevel=2',response=dict(status=200,data=data))
        return dict(requests=[response('440000',root),response('441900',city)])

    def test_official_api_preserves_direct_city_parent(self):
        data=module.parse_mca_snapshot(self.api_snapshot(),'44',1)
        self.assertEqual(data['441900001']['parent_code'],'441900')
        self.assertEqual(data['441900001']['level'],4)

    def test_official_api_rejects_missing_city_or_untrusted_origin(self):
        snapshot=self.api_snapshot()
        snapshot['requests'].pop()
        with self.assertRaisesRegex(ValueError,'coverage incomplete'):
            module.parse_mca_snapshot(snapshot,'44',1)
        snapshot=self.api_snapshot()
        snapshot['requests'][0]['url']=snapshot['requests'][0]['url'].replace('dmfw.mca.gov.cn','example.com')
        with self.assertRaisesRegex(ValueError,'Unexpected official API source'):
            module.parse_mca_snapshot(snapshot,'44',1)

    def test_official_api_filters_withdrawn_aliases_and_rejects_conflicts(self):
        snapshot=self.api_snapshot(('莞城街道','旧街道（已撤销）'))
        self.assertEqual(len(module.parse_mca_snapshot(snapshot,'44',1)),3)
        with self.assertRaisesRegex(ValueError,'Conflicting official API node'):
            module.parse_mca_snapshot(self.api_snapshot(('莞城街道','同码另一名称')),'44',1)

    def test_official_api_alias_resolution_is_explicit_and_closed(self):
        rule={'441900001':dict(name='莞城街道',observed_names=['莞城街道','已审查别名'])}
        result=module.parse_mca_snapshot(self.api_snapshot(('莞城街道','已审查别名')),'44',1,rule)
        self.assertEqual(result['441900001']['name'],'莞城街道')
        with self.assertRaisesRegex(ValueError,'Unreviewed official API alias'):
            module.parse_mca_snapshot(self.api_snapshot(('莞城街道','新出现的别名')),'44',1,rule)

    def test_direct_county_keeps_repository_compatibility_group(self):
        baseline=[dict(code='650000000000',name='新疆维吾尔自治区',level=1,parent_code=None),
                  dict(code='659000000000',name='自治区直辖县级行政区划',level=2,parent_code='650000000000')]
        entries={'650000':dict(code='650000',name='新疆维吾尔自治区',level=1,parent_code=None),
                 '659013':dict(code='659013',name='草湖市',level=3,parent_code='650000')}
        source=dict(province='65',url='https://dmfw.mca.gov.cn/',as_of=None,sha256='a'*64,expected_towns=0)
        patch=module.build_patch(source,entries,baseline)
        self.assertEqual(next(o for o in patch['operations'] if o['code']=='659013000000')['parent_code'],'659000000000')
        self.assertEqual(entries['659000']['name'],'自治区直辖县级行政区划')

if __name__=='__main__':unittest.main()
