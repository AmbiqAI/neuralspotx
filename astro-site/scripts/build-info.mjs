/*
 * Provenance for the footer: which neuralSPOT-X release the prose describes,
 * and which commit produced the HTML.
 *
 * The version is read from pyproject.toml rather than duplicated here because
 * release-please rewrites that file and nothing else on a release; a copy in
 * the site would go stale the first time a release lands without a docs change.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(site, '..');

const git = (...args) => {
  try {
    return execFileSync('git', args, {
      cwd: root,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return '';
  }
};

const pyproject = fs.readFileSync(path.join(root, 'pyproject.toml'), 'utf8');
/* Scoped to the [project] table: other tables carry their own `version` keys. */
const projectTable = pyproject.split(/^\[/m).find((table) => table.startsWith('project]'));
const version = projectTable?.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (!version) throw new Error('No version in the [project] table of pyproject.toml');

/* GITHUB_SHA is the fallback for a checkout without git history. */
const commit = git('rev-parse', 'HEAD') || process.env.GITHUB_SHA || '';
if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error('No source commit for the docs build');

const buildInfo = {
  version,
  commit,
  shortCommit: commit.slice(0, 8),
  sourceUrl: `https://github.com/AmbiqAI/neuralspotx/tree/${commit}`,
  commitTime: git('show', '-s', '--format=%cI', 'HEAD') || null,
  modified: Boolean(git('status', '--porcelain', '--untracked-files=normal')),
};

const json = `${JSON.stringify(buildInfo, null, 2)}\n`;
fs.mkdirSync(path.join(site, 'src/data'), { recursive: true });
fs.writeFileSync(path.join(site, 'src/data/build-info.json'), json);
fs.mkdirSync(path.join(site, 'public'), { recursive: true });
fs.writeFileSync(path.join(site, 'public/build-info.json'), json);

console.log(
  `Docs source: neuralspotx ${version}, ${buildInfo.shortCommit}${buildInfo.modified ? ' (local modifications)' : ''}`,
);
