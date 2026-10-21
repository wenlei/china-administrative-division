#!/usr/bin/env node
/** Replay an explicitly ordered annual update without changing historical years.
 * node scripts/materialize-official-update.mjs --baseline=/path/cache.db \
 *   --sources=updates/2026-10.sources.json --output=/path/new-directory
 * Output is published by directory rename only after all checks pass.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  DATABASE_SCHEMA,
  validatePatch,
} from '../packages/data-protocol/dist/index.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'packages/cli/package.json'));
const Database = require('better-sqlite3');
const get = (key) =>
  process.argv.find((a) => a.startsWith(`--${key}=`))?.slice(key.length + 3);

async function main() {
  const baselinePath = get('baseline');
  const outputArg = get('output');
  if (!baselinePath || !outputArg)
    throw new Error('--baseline and --output are required');
  if (!fs.existsSync(baselinePath))
    throw new Error('Baseline database does not exist');
  const manifestPath = path.resolve(
    get('sources') ?? path.join(root, 'updates/2026-10.sources.json')
  );
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const { target_year: year, baseline_year: baseYear, provinces } = manifest;
  const mainland = [
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
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(baseYear) ||
    year <= baseYear
  )
    throw new Error('Invalid target/baseline year');
  if (
    provinces.length !== 31 ||
    new Set(provinces.map((p) => p.province)).size !== 31 ||
    provinces.some(
      (p) =>
        !mainland.includes(p.province) ||
        !['included', 'pending'].includes(p.status)
    )
  ) {
    throw new Error(
      'Coverage must enumerate exactly the 31 mainland provinces with explicit status'
    );
  }
  const pending = provinces.filter((p) => p.status !== 'included');
  const outdated = provinces.filter(
    (p) => p.status === 'included' && (!p.as_of || p.as_of < `${year}-01-01`)
  );
  if (
    process.argv.includes('--require-complete') &&
    (pending.length || outdated.length)
  ) {
    throw new Error(
      `Not a complete current national snapshot: ${pending.length} pending; ${outdated.length} old/undated`
    );
  }
  const output = path.resolve(outputArg);
  if (fs.existsSync(output)) throw new Error(`Refusing to overwrite ${output}`);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const stage = fs.mkdtempSync(
    path.join(path.dirname(output), '.cndiv-update-')
  );
  const patchDir = path.join(stage, 'patches', String(year));
  fs.mkdirSync(patchDir, { recursive: true });
  let published = false;
  try {
    const db = new Database(path.join(stage, 'cache.db'));
    try {
      db.exec(DATABASE_SCHEMA);
      db.prepare('ATTACH DATABASE ? AS baseline').run(
        path.resolve(baselinePath)
      );
      const n = db
        .prepare('SELECT COUNT(*) AS n FROM baseline.divisions WHERE year=?')
        .get(baseYear).n;
      if (!n) throw new Error(`Baseline year ${baseYear} has no records`);
      db.prepare(
        'INSERT INTO divisions SELECT * FROM baseline.divisions WHERE year<>?'
      ).run(year);
    } finally {
      db.close();
    }
    const files = [
      ...manifest.base_patches,
      ...provinces.filter((p) => p.status === 'included').map((p) => p.patch),
      ...(manifest.extra_patches ?? []),
    ];
    const applied = [];
    for (const [index, file] of files.entries()) {
      const absolute = path.resolve(root, file);
      const bytes = fs.readFileSync(absolute);
      const checked = validatePatch(JSON.parse(bytes));
      if (!checked.success)
        throw new Error(`Invalid patch ${file}: ${checked.error}`);
      if (checked.data.meta.apply_after !== `${baseYear}-baseline`)
        throw new Error(`Baseline mismatch: ${file}`);
      const staged = path.join(
        patchDir,
        `${String(index).padStart(3, '0')}-${path.basename(file)}`
      );
      fs.writeFileSync(staged, bytes);
      const result = spawnSync(
        process.execPath,
        [
          path.join(root, 'packages/cli/dist/cli.js'),
          'apply-patch',
          `--patch=${staged}`,
          `--cache=${stage}`,
        ],
        { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 }
      );
      fs.appendFileSync(
        path.join(stage, 'replay.log'),
        `${file}\n${result.stdout ?? ''}${result.stderr ?? ''}\n`
      );
      if (result.error || result.status !== 0)
        throw new Error(
          `Patch failed: ${file}: ${result.error ?? result.stderr}`
        );
      applied.push({
        file,
        sha256: createHash('sha256').update(bytes).digest('hex'),
      });
    }
    const final = new Database(path.join(stage, 'cache.db'));
    const coverage = [];
    try {
      const dangling = final
        .prepare(
          `SELECT d.code,d.parent_code FROM divisions d
        LEFT JOIN divisions p ON p.code=d.parent_code AND p.year=d.year AND p.status='active'
        WHERE d.year=? AND d.status='active' AND d.level BETWEEN 2 AND 4 AND p.code IS NULL`
        )
        .all(year);
      if (dangling.length)
        throw new Error(
          `Active four-level nodes with missing/inactive parents: ${JSON.stringify(dangling.slice(0, 10))}`
        );
      const auditCount = final
        .prepare('SELECT COUNT(*) AS n FROM patch_history')
        .get().n;
      if (auditCount !== applied.length)
        throw new Error('Patch replay/audit count mismatch');
      // Compare every baseline field, rather than relying on counts alone.
      final
        .prepare('ATTACH DATABASE ? AS original')
        .run(path.resolve(baselinePath));
      const changed = final
        .prepare(
          `SELECT COUNT(*) AS n FROM (
        SELECT * FROM original.divisions WHERE year<>? EXCEPT SELECT * FROM main.divisions WHERE year<>?)`
        )
        .get(year, year).n;
      const extra = final
        .prepare(
          `SELECT COUNT(*) AS n FROM (
        SELECT * FROM main.divisions WHERE year<>? EXCEPT SELECT * FROM original.divisions WHERE year<>?)`
        )
        .get(year, year).n;
      if (changed || extra) throw new Error('Historical baseline changed');
      for (const p of provinces) {
        const counts = final
          .prepare(
            `SELECT level,COUNT(*) AS count FROM divisions
          WHERE year=? AND status='active' AND level<=4 AND substr(code,1,2)=? GROUP BY level`
          )
          .all(year, p.province);
        const towns = counts.find((c) => c.level === 4)?.count ?? 0;
        const expected = p.expected_current_towns ?? p.expected_towns;
        if (p.status === 'included' && towns !== expected)
          throw new Error(
            `${p.name}: expected ${expected} townships, got ${towns}`
          );
        coverage.push({
          province: p.province,
          name: p.name,
          status: p.status,
          as_of: p.as_of ?? null,
          source_url: p.url,
          source_sha256: p.sha256,
          source_kind: p.source_kind ?? 'provincial_table',
          retrieved_at: p.retrieved_at ?? p.checked_at,
          count_basis: p.count_basis,
          name_resolutions: p.name_resolutions,
          date_basis: p.date_basis,
          supplements: p.supplements ?? [],
          counts,
          reason: p.reason ?? '',
        });
      }
      const integrity = final.pragma('integrity_check', { simple: true });
      if (integrity !== 'ok') throw new Error(`SQLite integrity: ${integrity}`);
      const metadata = {
        edition: manifest.edition,
        complete_national: false,
        all_provinces_included: pending.length === 0,
        target_year: year,
        baseline_year: baseYear,
        baseline_unchanged: true,
        historical_years_unchanged: true,
        frozen_village_year: 2023,
        included_provinces: 31 - pending.length,
        pending_provinces: pending.map((p) => p.province),
        old_or_undated_provinces: outdated.map((p) => p.province),
        applied,
        coverage,
      };
      final
        .prepare('INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)')
        .run(`update-${manifest.edition}`, JSON.stringify(metadata));
      fs.writeFileSync(
        path.join(stage, 'coverage.json'),
        JSON.stringify(metadata, null, 2) + '\n'
      );
    } finally {
      final.close();
    }
    fs.rmSync(path.join(stage, 'patches'), { recursive: true });
    fs.renameSync(stage, output);
    published = true;
    console.log(
      `Published ${output}; ${31 - pending.length}/31 provinces have admitted official sources; ${pending.length} pending, ${outdated.length} old/undated. Historical ${baseYear} unchanged. Village level remains frozen.`
    );
  } finally {
    if (!published) fs.rmSync(stage, { recursive: true, force: true });
  }
}
main().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
