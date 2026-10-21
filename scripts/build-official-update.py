#!/usr/bin/env python3
"""Build existing-format annual patches from downloaded provincial official tables.

python scripts/build-official-update.py --sources updates/2026-10.sources.json \
  --raw /path/to/downloads --baseline /path/to/2023/cache.db --output patches/2026

Dependencies: beautifulsoup4, xlrd, openpyxl. PDF inputs use pdftotext -layout
before this command; their original PDF, not the extracted text, is hashed.
No network requests; no baseline changes. Only provinces explicitly admitted in
the source manifest are processed. Unavailable/image-only sources stay pending.
"""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

def clean(value):
    return re.sub(r'\s+', '', str(value or '')).replace('\x07', '')

def name_only(value):
    value = str(value).strip()
    # A leading parenthetical may spell a rare character, e.g. （门+合）山镇.
    if value and value[0] not in '（(':
        value = re.sub(r'[（(].*', '', value)
    return clean(value).rstrip('*＊')

def read_rows(path, kind):
    if kind == 'rows-json':
        return json.loads(path.read_text())
    if kind == 'html':
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(path.read_bytes(), 'html.parser')
        rows = [[td.get_text(' ', strip=True) for td in tr.find_all(['td','th'], recursive=False)]
                for tr in soup.select('tr') if not tr.find('tr')]
        # macOS textutil's DOC→HTML conversion may emit the first row outside <tr>.
        for td in soup.find_all('td'):
            if td.find_parent('tr') is None:
                prev=td.find_previous_sibling('td')
                rows.append([prev.get_text(' ',strip=True) if prev else '', td.get_text(' ',strip=True)])
        return rows
    if kind == 'xls':
        import xlrd
        book = xlrd.open_workbook(path)
        return [sheet.row_values(i) for sheet in book.sheets() for i in range(sheet.nrows)]
    if kind == 'xlsx':
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return [list(row) for sheet in book for row in sheet.iter_rows(max_col=12, values_only=True)]
    if kind == 'pdf-text':
        rows = []
        for line in path.read_text().splitlines():
            # Layout extraction is admitted only for single name/code-column PDFs.
            m = re.fullmatch(r'\s*(.*?)\s+(\d{6}|\d{9})\s*', line)
            if m:
                rows.append([re.sub(r'^\d+\s+', '', m[1]), m[2]])
        return rows
    raise ValueError(f'Unsupported parser: {kind}')

def parse_mca_snapshot(snapshot, province, expected_towns, resolutions=None):
    """Use the published parent tree; never infer a direct-administered parent."""
    entries = {}
    requested = set()
    root = None
    def walk(node, parent=None):
        code = str(node['code'])
        level = node['level']
        if not re.fullmatch(province+r'\d{10}', code) or level not in {1,2,3,4}:
            raise ValueError(f'Invalid official API node: {code}')
        # The public API mixes explicitly withdrawn units into its result tree.
        if re.search(r'[（(](?:已)?撤销[）)]', node['name']):
            return
        short = code[:9 if level == 4 else 6]
        name = node['name']
        resolution = (resolutions or {}).get(short)
        if resolution:
            if name not in resolution['observed_names'] or resolution['name'] not in resolution['observed_names']:
                raise ValueError(f'Unreviewed official API alias: {short}: {name}')
            name = resolution['name']
        row = dict(code=short, name=name, level=level, parent_code=parent)
        if short in entries and entries[short] != row:
            raise ValueError(f'Conflicting official API node: {short}')
        entries[short] = row
        for child in node.get('children', []):
            walk(child, short)
    for request in snapshot['requests']:
        from urllib.parse import urlparse, parse_qs
        url = urlparse(request['url'])
        if url.scheme != 'https' or url.netloc != 'dmfw.mca.gov.cn' or url.path != '/9095/xzqh/getList':
            raise ValueError('Unexpected official API source')
        query = parse_qs(url.query)
        code = query.get('code', [''])[0]
        response = request['response']
        node = response.get('data')
        if response.get('status') != 200 or not node or node['code'][:6] != code:
            raise ValueError(f'Incomplete official API response: {code}')
        if query.get('maxLevel') != ['2'] or code in requested:
            raise ValueError(f'Invalid/repeated official API request: {code}')
        requested.add(code)
        if code == province+'0000':
            root = node
            walk(node)
    if root is None:
        raise ValueError('Official API province root missing')
    expected_requests = {province+'0000'} | {n['code'][:6] for n in root.get('children', [])
        if n['level'] <= 3 and not re.search(r'[（(](?:已)?撤销[）)]', n['name'])}
    if requested != expected_requests:
        raise ValueError('Official API city/direct-county request coverage incomplete')
    for request in snapshot['requests']:
        node = request['response']['data']
        if node['level'] > 1:
            parent = entries[node['code'][:6]]['parent_code']
            walk(node, parent)
    if sum(r['level'] == 4 for r in entries.values()) != expected_towns:
        raise ValueError('Official API township count mismatch')
    return entries

def parse_table(rows, province, root_name, expected_towns):
    entries = {}
    def put(code, name):
        name = name_only(name)
        if not name or not re.search('[\u3400-\u9fff]', name):
            raise ValueError(f'Invalid name for {code}: {name!r}')
        if code in entries and entries[code]['name'] != name:
            raise ValueError(f'Conflicting duplicate {code}: {entries[code]["name"]!r} / {name!r}')
        level = 4 if len(code)==9 else 1 if code.endswith('0000') else 2 if code.endswith('00') else 3
        parent = None if level==1 else province+'0000' if level==2 else code[:4]+'00' if level==3 else code[:6]
        entries[code] = dict(code=code, name=name, level=level, parent_code=parent)
    put(province+'0000', root_name)
    for row in rows:
        cells = [str(int(v)) if isinstance(v,(int,float)) else str(v or '') for v in row]
        # Name/code pairs and the embedded six-digit upper-level cells in merged sheets.
        for i,cell in enumerate(cells):
            compact = clean(cell)
            if re.fullmatch(province+r'(?:\d{4}|\d{7})', compact):
                if i: put(compact,cells[i-1])
            elif len(cell)<250:
                m = re.match(r'\s*([^\d]+?)\s*('+province+r'\d{4})(?!\d)',cell)
                if m: put(m[2],m[1])
        # Tianjin and Chongqing explicitly list county names but omit separate county codes.
        if province in {'12','22','50'}:
            towns = [clean(c) for c in cells if re.fullmatch(province+r'\d{7}',clean(c))]
            if towns:
                col = 2 if province in {'12','22'} else 1
                county_cell = cells[col] if len(cells)>col and (province!='50' or len(cells)>=4) else ''
                if name_only(county_cell) and not re.fullmatch(r'\d+',clean(county_cell)):
                    put(towns[0][:6],county_cell)
                if province=='22' and name_only(cells[1]):
                    put(towns[0][:4]+'00',cells[1])
    towns = [r for r in entries.values() if r['level']==4]
    if len(towns)!=expected_towns:
        raise ValueError(f'{province}: expected {expected_towns} townships, parsed {len(towns)}')
    # Every real county must occur explicitly in this same source; no name guessing.
    missing = sorted({r['parent_code'] for r in towns if r['parent_code'] not in entries})
    if missing: raise ValueError(f'{province}: missing explicit parent names: {missing[:20]}')
    return entries

def build_patch(source, entries, baseline):
    prefix = source['province']
    base = {r['code'][:9 if r['level']==4 else 6]:dict(r) for r in baseline
            if r['code'].startswith(prefix) and r['level']<=4}
    # The API flattens province-direct county units. The repository retains its
    # existing xx9000 grouping node; it is a compatibility group, not a new entity.
    for row in entries.values():
        if row['level']==3 and row['parent_code']==prefix+'0000' and row['code'][2:4]=='90':
            group=row['code'][:4]+'00'
            if group not in base:
                raise ValueError(f'{prefix}: historical direct-county group missing: {group}')
            row['parent_code']=group
    # Existing intermediate placeholders remain solely for compatible historical hierarchy.
    for row in list(entries.values()):
        p=row['parent_code']
        if p and p not in entries:
            old=base.get(p)
            if not old: raise ValueError(f'{prefix}: unknown upper parent {p}')
            entries[p]=dict(code=p,name=old['name'],level=old['level'],parent_code=old['parent_code'][:6] if old['parent_code'] else None)
    operations=[]
    for code,row in sorted(entries.items()):
        full=code.ljust(12,'0');parent=row['parent_code'].ljust(12,'0') if row['parent_code'] else None
        prev=base.get(code)
        if not prev:
            operations.append(dict(op='add',code=full,name=row['name'],level=row['level'],parent_code=parent,
                                   source_type='mca_decree',confidence_score=100))
        else:
            # Replay follows earlier-year events. Their target state can differ
            # from 2023 even when this source agrees with the original baseline.
            changes=dict(name=row['name'],status='active')
            if parent:changes['new_parent']=parent
            operations.append(dict(op='update',code=full,**changes))
    for code,row in sorted(base.items()):
        if code not in entries:
            operations.append(dict(op='update',code=row['code'],status='deprecated',
                note='不在本期民政全量名录，退出2026四级视图；不等同于统计单位实体撤销，旧年度记录保留。'))
    return dict(meta=dict(author='wenlei-official-2026-10',source_url=source['url'],evidence_confidence='high',
        apply_after='2023-baseline',source_pipeline='community',created_at=source.get('checked_at','2026-10-20')+'T00:00:00.000Z',
        notes=f"2026年10月整理；官方数据截止{source['as_of'] or '未注明，不能认定2026现势'}；原件SHA-256={source['sha256']}；"
              '仅校准省至乡四级，村级仍为冻结历史基线，不得据此视为现势村级；'
              'NBS与民政存在同码异名/异码同名，变更只作用于目标2026分区；'
              f"本表乡级{source['expected_towns']}条。" + source.get('reason','')),operations=operations)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--raw',type=Path,required=True)
    ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();manifest=json.loads(a.sources.read_text())
    db=sqlite3.connect(f'file:{a.baseline}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    baseline=db.execute('select * from divisions where year=2023 and level<=4').fetchall();db.close()
    if not baseline:raise ValueError('2023 baseline missing')
    a.output.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for s in manifest['provinces']:
        if s['status']!='included':continue
        raw=a.raw/s['file'];original=a.raw/s.get('original_file',s['file'])
        actual=hashlib.sha256(original.read_bytes()).hexdigest()
        if actual!=s['sha256']:raise ValueError(f"{s['province']}: original SHA-256 mismatch")
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=s['parsed_sha256']:
            raise ValueError(f"{s['province']}: parsed input SHA-256 mismatch")
        if s['parser'] == 'mca-snapshot':
            entries=parse_mca_snapshot(json.loads(raw.read_text()),s['province'],s['expected_towns'],s.get('name_resolutions'))
        else:
            entries=parse_table(read_rows(raw,s['parser']),s['province'],s['name'],s['expected_towns'])
        patch=build_patch(s,entries,baseline)
        output=a.output/s['patch'].split('/')[-1]
        if patch['operations']:outputs.append((output,patch))
        print(s['province'],len(entries),'nodes',len(patch['operations']),'operations',flush=True)
    # Validate all admitted sources before writing any patch.
    for output,patch in outputs:
        output.write_text(json.dumps(patch,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
