#!/usr/bin/env python3
"""Extract archived Hebei/Zhejiang PDF tables and Qinghai DOC text to rows-json.

Requires pdfplumber. Convert Qinghai DOC with macOS textutil -convert txt first.
Coordinates describe these archived source editions, not arbitrary PDF tables.
"""
import argparse
import json
from pathlib import Path
import re


def pdf_rows(path, province):
    import pdfplumber
    towns, counties = {}, {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            codes = [w for w in words if re.fullmatch(province+r'\d{7}', w['text'])]
            for code in codes:
                names = [w for w in words if
                    (310 < w['x0'] < 425 if province == '13' else 420 < w['x0'] < 550)
                    and abs(w['top']-code['top']) < 3]
                if not names:
                    raise ValueError(f"Missing township name: {code['text']}")
                name = ''.join(w['text'] for w in sorted(names, key=lambda w: w['x0']))
                old = towns.setdefault(code['text'], name)
                if old != name:
                    raise ValueError('Conflicting township name')
            for word in words:
                if not (200 < word['x0'] < 310 if province == '13' else 270 < word['x0'] < 420):
                    continue
                if province == '33' and word['text'] == '龙港市':
                    # This county has no township layer; the original table lists it alone.
                    counties['330383'] = '龙港市'
                    continue
                if '行政区划' in word['text'] or not re.search('(区|县|市)$', word['text']) or not codes:
                    continue
                nearest = min(codes, key=lambda c: abs(word['top']-c['top']))
                county = nearest['text'][:6]
                old = counties.setdefault(county, word['text'])
                if old != word['text']:
                    raise ValueError(f'Conflicting county name: {county}')
    missing = {c[:6] for c in towns} - counties.keys()
    if missing:
        raise ValueError(f'Missing county labels: {sorted(missing)}')
    # Embedded PDF text omits these glyphs. Checked against the rendered originals
    # and independently retrieved MCA API text; never apply a fuzzy replacement.
    restorations = {'13': {'130207110': ('柳树镇', '柳树𨟠镇')},
                    '33': {'330902105': ('干镇', '干𬒗镇')}}
    for code, (extracted, restored) in restorations[province].items():
        if towns.get(code) not in {extracted, restored}:
            raise ValueError(f'Unexpected rare-character source: {code}')
        towns[code] = restored
    return [[n,c] for c,n in sorted(counties.items())] + [[n,c] for c,n in sorted(towns.items())]


def qinghai_rows(text):
    rows = []
    for match in re.finditer(r'([^\d\s\x07]+(?:\s*[^\d\s\x07]+)?)\s+(63\d{4})(?!\d)', text):
        name = match[1].splitlines()[-1].split('\x07')[-1]
        rows.append([name, match[2]])
    lines = text.replace('\x07', '\n').splitlines()
    for i, line in enumerate(lines):
        if re.fullmatch(r'63\d{7}', line.strip()):
            rows.append([lines[i-1].strip(), line.strip()])
    if sum(len(code)==9 for _,code in rows) != 405:
        raise ValueError('Incomplete Qinghai DOC extraction')
    return rows


def ruled_pdf_rows(path):
    """Shanxi/Ningxia 2026 editions: explicit merged name/code cells."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [row for page in pdf.pages for table in page.extract_tables() for row in table]


def guangdong_rows(path):
    """49-page June 2026 table; its headings explicitly identify city/county names."""
    import pdfplumber
    towns, upper = {}, {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for table in page.extract_tables():
                for row in table:
                    if len(row) != 4:
                        continue
                    city, county, _, code = [re.sub(r'\s+', '', value or '') for value in row]
                    if not re.fullmatch(r'44\d{7}', code):
                        continue
                    word = next(w for w in words if w['text']==code)
                    name = ''.join(w['text'] for w in sorted(
                        [w for w in words if 220<w['x0']<410 and abs(w['top']-word['top'])<3],
                        key=lambda w:w['x0']))
                    towns[code] = name
                    if city:
                        upper[code[:4]+'00'] = city
                    if county:
                        upper[code[:6]] = county
    # Embedded PDF text omits these glyphs. Restored after original-page visual
    # review and same-code MCA text corroboration. No fuzzy/global replacement.
    restorations = {'440511006':('莲街道','𬶍莲街道'), '440511007':('江街道','𬶍江街道'),
        '440512001':('石街道','𬒈石街道'), '440883107':('塘镇','塘㙍镇'),
        '441423115':('隍镇','𨻧隍镇'), '441721100':('织镇','织𬕂镇'),
        '441781101':('河镇','河㙟镇'), '441881120':('下镇','下𱳪镇'),
        '445381106':('塘镇','𬜯塘镇')}
    for code,(extracted,restored) in restorations.items():
        if towns.get(code) not in {extracted,restored}:
            raise ValueError(f'Unexpected Guangdong rare-character source: {code}')
        towns[code]=restored
    if len(towns)!=1607 or len(upper)!=143:
        raise ValueError('Incomplete Guangdong table')
    return [[name,code] for code,name in sorted(upper.items())] + [[name,code] for code,name in sorted(towns.items())]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=Path, required=True)
    args = parser.parse_args()
    outputs = {province: pdf_rows(args.raw/('13-2026.pdf' if province=='13' and (args.raw/'13-2026.pdf').exists() else province+'-attachment-0.pdf'), province) for province in ['13','33']}
    outputs['63'] = qinghai_rows((args.raw/'63-attachment-0.txt').read_text())
    # Optional follow-up editions; older archives remain usable.
    for province in ['14','64']:
        file=args.raw/(province+'-2026.pdf')
        if file.exists():
            outputs[province]=ruled_pdf_rows(file)
    if (args.raw/'44-2026.pdf').exists():
        outputs['44']=guangdong_rows(args.raw/'44-2026.pdf')
    for province, rows in outputs.items():
        (args.raw/(province+'-parsed.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
