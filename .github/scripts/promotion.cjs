'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

function validateFormat(m) {
  assert.equal(m.schema, 1, 'Manifest schema');
  assert.match(m.source_commit, /^[0-9a-f]{40}$/);
  assert.match(m.source_tree, /^[0-9a-f]{40}$/);
  assert.match(m.version, /^\d+\.\d+\.\d+$/);
  assert.match(m.sha256, /^[0-9a-f]{64}$/);
  assert.equal(m.installer, `MAJIMeeting-${m.version}-preview-Setup.exe`);
  for (const key of ['run_id', 'run_number', 'run_attempt']) {
    assert.ok(Number.isSafeInteger(m[key]) && m[key] > 0, key);
  }
}

function validatePromotion(m, {repository, targetTree, run, pr, sourceCommit}) {
  validateFormat(m);
  assert.equal(m.repository, repository, 'Manifest repository');
  assert.equal(run.repository.full_name, repository, 'Run repository');
  assert.equal(run.head_repository.full_name, repository, 'Foreign head repository');
  assert.equal(pr.head.repo.full_name, repository, 'Fork builds are not promoted');
  assert.equal(pr.base.repo.full_name, repository);
  assert.equal(pr.merged, true, 'PR must be merged');
  assert.equal(pr.base.ref, 'main');
  assert.equal(run.path, '.github/workflows/ci.yml');
  assert.equal(run.event, 'pull_request');
  assert.equal(run.status, 'completed');
  assert.equal(run.conclusion, 'success');
  assert.equal(run.head_sha, pr.head.sha, 'Stale PR head');
  assert.equal(m.pr_number, pr.number);
  assert.equal(m.run_id, run.id);
  assert.equal(m.run_number, run.run_number);
  assert.equal(m.run_attempt, run.run_attempt);
  assert.equal(m.source_tree, targetTree, 'Tested tree differs from merged tree');
  assert.equal(sourceCommit.sha, m.source_commit);
  assert.equal(sourceCommit.tree.sha, targetTree, 'Source commit tree mismatch');
  assert.ok(sourceCommit.sha === pr.head.sha || sourceCommit.parents.some(p => p.sha === pr.head.sha),
            'Tested commit must include the PR head');
}

function verifyBundle(directory, expected = {}) {
  const raw = fs.readFileSync(path.join(directory, 'build-manifest.json'));
  const m = JSON.parse(raw);
  validateFormat(m);
  if (expected.manifestDigest) {
    assert.equal(crypto.createHash('sha256').update(raw).digest('hex'), expected.manifestDigest,
                 'Bundle manifest differs from the approved manifest');
  }
  if (expected.repository) assert.equal(m.repository, expected.repository);
  if (expected.runId) assert.equal(m.run_id, Number(expected.runId));
  if (expected.targetTree) assert.equal(m.source_tree, expected.targetTree);
  const file = path.join(directory, m.installer);
  assert.ok(fs.lstatSync(file).isFile() && !fs.lstatSync(file).isSymbolicLink());
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'), m.sha256,
               'Installer digest mismatch');
  return m;
}

async function selectCandidate({github, context, core}) {
  core.setOutput('candidate', '');
  if (context.eventName !== 'push' || context.ref !== 'refs/heads/main') return;
  const {owner, repo} = context.repo;
  const prs = await github.paginate(github.rest.repos.listPullRequestsAssociatedWithCommit,
                                    {owner, repo, commit_sha: context.sha, per_page: 100});
  const pr = prs.find(p => p.merged_at && p.merge_commit_sha === context.sha &&
                          p.base.ref === 'main' && p.head.repo?.full_name === `${owner}/${repo}`);
  if (!pr) return core.info('No merged same-repository PR: full validation required.');
  const {data} = await github.rest.actions.listWorkflowRuns({owner, repo, workflow_id: 'ci.yml',
    event: 'pull_request', status: 'success', head_sha: pr.head.sha, per_page: 20});
  for (const run of data.workflow_runs) {
    const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts,
                                           {owner, repo, run_id: run.id, per_page: 100});
    if (['MAJIMeeting-build-manifest', 'MAJIMeeting-Windows-preview'].every(
        name => artifacts.some(a => a.name === name && !a.expired))) {
      core.setOutput('candidate', String(run.id));
      core.setOutput('pr', String(pr.number));
      return;
    }
  }
  core.info('No usable successful build: full validation required.');
}

async function approveCandidate({github, context, core, directory, runId, prNumber}) {
  core.setOutput('reuse', 'false');
  try {
    const {owner, repo} = context.repo;
    const m = JSON.parse(fs.readFileSync(path.join(directory, 'build-manifest.json')));
    const [run, pr, target, source] = await Promise.all([
      github.rest.actions.getWorkflowRun({owner, repo, run_id: Number(runId)}),
      github.rest.pulls.get({owner, repo, pull_number: Number(prNumber)}),
      github.rest.git.getCommit({owner, repo, commit_sha: context.sha}),
      github.rest.git.getCommit({owner, repo, commit_sha: m.source_commit})
    ]);
    assert.equal(pr.data.merge_commit_sha, context.sha);
    validatePromotion(m, {repository: `${owner}/${repo}`, targetTree: target.data.tree.sha,
                          run: run.data, pr: pr.data, sourceCommit: source.data});
    const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun,
                                      {owner, repo, run_id: Number(runId), per_page: 100});
    assert.ok(jobs.some(j => j.name === 'windows-package' && j.conclusion === 'success'));
    core.setOutput('reuse', 'true');
    core.setOutput('source_run', String(m.run_id));
    core.setOutput('manifest_digest', crypto.createHash('sha256').update(
      fs.readFileSync(path.join(directory, 'build-manifest.json'))).digest('hex'));
    core.info(`Approved installer from run ${m.run_id}; tested and merged Git trees match.`);
  } catch (error) {
    core.warning(`Artifact cannot be promoted; rebuilding with full checks: ${error.message}`);
  }
}

module.exports = {validateFormat, validatePromotion, verifyBundle, selectCandidate, approveCandidate};
