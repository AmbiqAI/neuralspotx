// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * Proves the Python reference toolchain runs against the real package, ahead
 * of wiring it into the build (AmbiqAI/neuralspotx#258).
 *
 * Nothing is committed and nothing is read back: this only has to fail loudly
 * if griffe or helia-ui's pyref cannot process `neuralspotx` at all. The
 * griffe pin matches the one the migration plan validated against; a floating
 * version would turn an upstream schema change into a red docs build on an
 * unrelated pull request.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(site, '..');
const scratch = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'nsx-pyref-'));
const dump = path.join(scratch, 'griffe.json');

const run = (label, command, args, options = {}) => {
  const started = Date.now();
  const result = spawnSync(command, args, { stdio: ['ignore', 'pipe', 'inherit'], ...options });
  if (result.error) throw new Error(`${label} could not start: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`${label} exited ${result.status}`);
  console.log(`${label}: ${((Date.now() - started) / 1000).toFixed(1)}s`);
  return result.stdout;
};

try {
  fs.writeFileSync(
    dump,
    run('griffe dump', 'uv', [
      'run',
      '--with',
      'griffe==1.7.3',
      'griffe',
      'dump',
      'neuralspotx',
      '--docstyle',
      'google',
      '-f',
    ], { cwd: root, maxBuffer: 512 * 1024 * 1024 }),
  );

  run('helia-ui-pyref', process.execPath, [
    path.join(site, 'node_modules/@ambiqai/helia-ui/scripts/pyref.mjs'),
    '--input', dump,
    '--out', path.join(scratch, 'pyref/api'),
    '--public', path.join(scratch, 'pyref/public'),
    '--base', '/neuralspotx/',
    '--package', 'neuralspotx',
    '--quiet',
  ], { cwd: site });

  const pages = fs
    .readdirSync(path.join(scratch, 'pyref/api'), { recursive: true })
    .filter((entry) => String(entry).endsWith('index.mdx')).length;
  console.log(`pyref smoke passed: ${pages} reference pages rendered, none published.`);
} finally {
  fs.rmSync(scratch, { recursive: true, force: true });
}
