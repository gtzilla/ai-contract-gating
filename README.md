# ai-contract-gating

A tiny proof-of-concept showing contract-based gating as an external authority check for AI-assisted code changes.

This repository is intentionally small and local.

It demonstrates one narrow idea:

**A change can look locally plausible, but still violate preserved truth.  
If that truth is bound to explicit contract clauses and checked independently, the change can be blocked automatically.**

## What this repo proves

This repo contains:

- a small filesystem reconciler
- a human-readable contract
- a machine-readable manifest
- frozen fixtures
- a checker that maps fixture outcomes to clause results
- a GitHub Actions workflow that runs the checker on pull requests

The point is not to prove general software correctness.

The point is to prove that a contract can live outside the implementation and still govern whether a proposed change is allowed to pass.

## Governing rule

The contract in this repo is intentionally narrow.

Managed files inside a unit directory are:

- `doc.txt`
- `meta.json`

Any other file in that unit directory is treated as manual.

For the fixture package, the canonical manual file is:

- `manual.txt`

The core preserved truth is:

**Manual files inside managed unit directories must survive every required directory-mutating operation.**

For this repo, the required mutation surfaces are:

- delete
- overwrite
- reset

## Repository structure

- `contract/`
  - human-readable authority documents
  - machine-readable manifest
- `fixtures/`
  - frozen filesystem cases used by the checker
- `src/reconcile.py`
  - the tiny reconciler under test
- `src/check_contract.py`
  - the contract gate
- `.github/workflows/ci.yaml`
  - pull request workflow that runs the checker

## Clause model

The checker currently evaluates these clauses:

- `MC-DEL-1`
- `MC-OVR-1`
- `MC-RST-1`
- `MC-POL-1`
- `MC-GLOB-1`

`MC` means:

**Mini Contract**

`MC-GLOB-1` is the aggregate clause.

It passes only if the required preservation surfaces all pass.

## How the checker works

The checker does not interpret prose at runtime.

It does something narrower:

1. Load the manifest.
2. Run the manifest-bound fixtures in isolated temporary workspaces.
3. Compare actual filesystem results to expected results.
4. Map those results to clause outcomes.
5. Compute aggregate clause outcomes.
6. Exit nonzero if any BLOCK clause fails.

That makes it usable both:

- locally
- in CI on pull requests

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run the gate locally

```bash
python src/check_contract.py
```

If all currently bound clauses pass, the checker exits `0`.

If any BLOCK clause fails, the checker exits `1`.

It also writes a JSON summary to:

```text
artifacts/check_contract_summary.json
```

## Why there are red and green pull requests

This repo is meant to show both sides of the gate.

A good demonstration requires:

- one pull request that fails because it violates preserved truth
- one pull request that passes because it remains conformant

The red case shows that the gate blocks a plausible but non-conformant change.

The green case shows that a different implementation can still be accepted if it preserves the bound truths.

## How to read this repo

If you only read three things, read these:

1. `contract/contract-v0.2.md`
2. `contract/manifest.yaml`
3. `src/check_contract.py`

That is the smallest path through the repo’s authority model:

- the contract defines what must stay true
- the manifest binds clauses to checks
- the checker enforces those checks

## What this repo is not

This is not:

- a general policy engine
- a full formal verification system
- a universal contract framework
- a claim that all software correctness can be reduced to fixtures

It is a small, explicit proof that contract-bound gating can create real consequence outside the implementation itself.

## Why this repo exists

This project exists to make one narrow point mechanically visible:

**A contract does not have to be just documentation.**

If it is bound to independent checks and used to gate pull requests, it becomes an externalized control surface over change.
