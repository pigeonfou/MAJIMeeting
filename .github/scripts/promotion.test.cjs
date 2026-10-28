'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {validatePromotion, verifyBundle} = require('./promotion.cjs');

function example() {
  const repository = 'pigeonfou/MAJIMeeting';
  const m = {schema: 1, repository, source_commit: 'a'.repeat(40), source_tree: 'b'.repeat(40),
    version: '0.2.6', installer: 'MAJIMeeting-0.2.6-preview-Setup.exe', sha256: 'c'.repeat(64),
    run_id: 100, run_number: 41, run_attempt: 1, pr_number: 9};
  const state = {repository, targetTree: m.source_tree,
    run: {repository: {full_name: repository}, head_repository: {full_name: repository},
      path: '.github/workflows/ci.yml', event: 'pull_request', status: 'completed',
      conclusion: 'success', head_sha: 'd'.repeat(40), id: 100, run_number: 41, run_attempt: 1},
    pr: {merged: true, number: 9, head: {repo: {full_name: repository}, sha: 'd'.repeat(40)},
      base: {repo: {full_name: repository}, ref: 'main'}},
    sourceCommit: {sha: m.source_commit, tree: {sha: m.source_tree}, parents: [{sha: 'd'.repeat(40)}]}};
  return {m, state};
}

test('same tested and merged content can be promoted across different commit IDs', () => {
  const {m, state} = example();
  validatePromotion(m, state);
});

for (const [name, mutate] of [
  ['changed merged source', (m, s) => { s.targetTree = 'e'.repeat(40); }],
  ['stale PR head', (m, s) => { s.pr.head.sha = 'e'.repeat(40); }],
  ['failed tests', (m, s) => { s.run.conclusion = 'failure'; }],
  ['fork artifact', (m, s) => { s.pr.head.repo.full_name = 'other/MAJIMeeting'; }],
  ['wrong workflow', (m, s) => { s.run.path = '.github/workflows/other.yml'; }],
  ['wrong attempt', m => { m.run_attempt = 2; }],
  ['wrong PR', m => { m.pr_number = 10; }],
  ['arbitrary source commit', (m, s) => { s.sourceCommit.parents = []; }],
  ['unsafe installer filename', m => { m.installer = '../untrusted.exe'; }]
]) {
  test(`rejects ${name}`, () => {
    const {m, state} = example();
    mutate(m, state);
    assert.throws(() => validatePromotion(m, state));
  });
}

test('bundle verification rejects modified installer or substituted manifest', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'majimeeting-promotion-'));
  try {
    const {m} = example();
    const bytes = Buffer.from('deterministic installer fixture');
    m.sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
    const raw = JSON.stringify(m);
    fs.writeFileSync(path.join(directory, m.installer), bytes);
    fs.writeFileSync(path.join(directory, 'build-manifest.json'), raw);
    const expected = {repository: m.repository, runId: m.run_id, targetTree: m.source_tree,
      manifestDigest: crypto.createHash('sha256').update(raw).digest('hex')};
    assert.equal(verifyBundle(directory, expected).sha256, m.sha256);
    fs.writeFileSync(path.join(directory, m.installer), 'modified');
    assert.throws(() => verifyBundle(directory, expected), /Installer digest mismatch/);
    fs.writeFileSync(path.join(directory, m.installer), bytes);
    fs.writeFileSync(path.join(directory, 'build-manifest.json'), JSON.stringify({...m, run_number: 99}));
    assert.throws(() => verifyBundle(directory, expected), /manifest differs/);
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
});
