import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Database from 'better-sqlite3';
import {
  mkdtempSync,
  writeFileSync,
  rmSync,
  existsSync,
  readFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { DATABASE_SCHEMA } from '@cndiv/data-protocol';
import { applyPatch } from '../dist/apply-patch.js';

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../..'
);
const codes = [
  '11',
  '12',
  '13',
  '14',
  '15',
  '21',
  '22',
  '23',
  '31',
  '32',
  '33',
  '34',
  '35',
  '36',
  '37',
  '41',
  '42',
  '43',
  '44',
  '45',
  '46',
  '50',
  '51',
  '52',
  '53',
  '54',
  '61',
  '62',
  '63',
  '64',
  '65',
];
let dir: string;
let baseline: string;
let patch: string;
let manifest: string;
beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), 'cndiv-official-update-'));
  baseline = path.join(dir, 'baseline.db');
  patch = path.join(dir, 'source.json');
  manifest = path.join(dir, 'sources.json');
  const db = new Database(baseline);
  db.exec(DATABASE_SCHEMA);
  const ins = db.prepare(
    'INSERT INTO divisions(code,name,level,parent_code,year,status) VALUES (?,?,?,?,?,?)'
  );
  for (const year of [2022, 2023]) {
    ins.run('110000000000', '北京市', 1, null, year, 'active');
    ins.run('110100000000', '市辖区', 2, '110000000000', year, 'active');
    ins.run('110101000000', '东城区', 3, '110100000000', year, 'active');
    ins.run('110101001000', '旧名称', 4, '110101000000', year, 'active');
  }
  db.close();
  writePatch([{ op: 'update', code: '110101001000', name: '官方名称' }]);
  writeFileSync(
    manifest,
    JSON.stringify({
      edition: '2026-10',
      target_year: 2026,
      baseline_year: 2023,
      base_patches: [],
      provinces: codes.map((province) =>
        province === '11'
          ? {
              province,
              name: '北京',
              status: 'included',
              as_of: '2026-06-30',
              expected_towns: 1,
              patch,
            }
          : {
              province,
              name: province,
              status: 'pending',
              reason: 'source unavailable',
            }
      ),
    })
  );
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));
function writePatch(operations: unknown[]) {
  writeFileSync(
    patch,
    JSON.stringify({
      meta: { author: 'test', apply_after: '2023-baseline' },
      operations,
    })
  );
}
function run(extra: string[] = []) {
  return spawnSync(
    process.execPath,
    [
      path.join(root, 'scripts/materialize-official-update.mjs'),
      `--baseline=${baseline}`,
      `--sources=${manifest}`,
      `--output=${path.join(dir, 'result')}`,
      ...extra,
    ],
    { encoding: 'utf8' }
  );
}
describe('dated official annual replay', () => {
  it('preserves every historical year and publishes explicit partial coverage', () => {
    const result = run();
    expect(result.status, result.stderr).toBe(0);
    const db = new Database(path.join(dir, 'result/cache.db'));
    const rows = db
      .prepare('SELECT year,name FROM divisions WHERE code=? ORDER BY year')
      .all('110101001000');
    expect(rows).toEqual([
      { year: 2022, name: '旧名称' },
      { year: 2023, name: '旧名称' },
      { year: 2026, name: '官方名称' },
    ]);
    db.close();
    const coverage = JSON.parse(
      readFileSync(path.join(dir, 'result/coverage.json'), 'utf8')
    );
    expect(coverage.complete_national).toBe(false);
    expect(coverage.pending_provinces).toHaveLength(30);
  });
  it('refuses a nationwide completeness claim before creating output', () => {
    const result = run(['--require-complete']);
    expect(result.status).not.toBe(0);
    expect(existsSync(path.join(dir, 'result'))).toBe(false);
  });
  it('rejects an inactive parent and publishes no broken database', () => {
    writePatch([{ op: 'update', code: '110101000000', status: 'deprecated' }]);
    const result = run();
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain('missing/inactive parents');
    expect(existsSync(path.join(dir, 'result'))).toBe(false);
    const db = new Database(baseline, { readonly: true });
    expect(
      db
        .prepare('SELECT status FROM divisions WHERE code=? AND year=2023')
        .get('110101000000')
    ).toEqual({ status: 'active' });
    db.close();
  });
  it('rejects duplicate province coverage instead of accepting a count of 31', () => {
    const m = JSON.parse(readFileSync(manifest, 'utf8'));
    m.provinces[1] = m.provinces[0];
    writeFileSync(manifest, JSON.stringify(m));
    expect(run().status).not.toBe(0);
    expect(existsSync(path.join(dir, 'result'))).toBe(false);
  });
  it('missing patch or invalid schema fails the CLI rather than exiting successfully', async () => {
    await expect(
      applyPatch({ patch: path.join(dir, 'missing.json') })
    ).rejects.toThrow('not found');
    writeFileSync(patch, '{}');
    await expect(applyPatch({ patch })).rejects.toThrow('Invalid patch');
    const result = spawnSync(
      process.execPath,
      [
        path.join(root, 'packages/cli/dist/cli.js'),
        'apply-patch',
        `--patch=${patch}`,
      ],
      { encoding: 'utf8' }
    );
    expect(result.status).not.toBe(0);
  });

  it('rejects an invalid baseline declaration or an empty baseline without partial rows', async () => {
    const cache = new Database(path.join(dir, 'cache.db'));
    cache.exec(DATABASE_SCHEMA);
    cache.close();
    writePatch([{ op: 'update', code: '110101001000', name: '官方名称' }]);
    await expect(applyPatch({ patch, cacheDir: dir })).rejects.toThrow(
      '基线年'
    );
    const empty = new Database(path.join(dir, 'cache.db'));
    expect(empty.prepare('SELECT COUNT(*) AS n FROM divisions').get()).toEqual({
      n: 0,
    });
    expect(
      empty.prepare('SELECT COUNT(*) AS n FROM patch_history').get()
    ).toEqual({ n: 0 });
    empty.close();
    const data = JSON.parse(readFileSync(patch, 'utf8'));
    data.meta.apply_after = 'unknown';
    writeFileSync(patch, JSON.stringify(data));
    await expect(applyPatch({ patch, cacheDir: dir })).rejects.toThrow(
      'Invalid baseline'
    );
  });
});
