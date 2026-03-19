# **Mini Reconciler Implementation Plan v0.1**

**Version 0.1**

## **1\. Purpose**

This plan defines the minimum implementation work required to make the Mini Reconciler repo operational.

The goal is not to build a general synchronization system.

The goal is to build the smallest possible local system that proves this claim:

**A contract-bound CI gate can fail a pull request when a change violates preserved truth across required mutation surfaces.**

## **2\. Scope**

This implementation covers only:

* one tiny local reconciler

* one manifest-bound checker

* one small fixture package

* one GitHub Actions pull request gate

This implementation does **not** attempt to provide:

* generalized contract execution

* LLM-based runtime reasoning

* remote services

* MCP integration

* generalized policy infrastructure

* full software correctness

## **3\. Frozen Repo Shape**

mini-reconciler/  
 README.md  
 contract/  
   contract-v0.2.md  
   fixture-package-spec-v0.1.md  
   checker-spec-v0.1.md  
   implementation-plan-v0.1.md  
   manifest.yaml  
 fixtures/  
   delete\_preserves\_manual\_file/  
   overwrite\_preserves\_manual\_file/  
   reset\_preserves\_manual\_file/  
   stale\_unit\_blocked\_when\_deletions\_disabled/  
 src/  
   reconcile.py  
   check\_contract.py  
 .github/  
   workflows/  
     ci.yaml  
 artifacts/  
   .gitkeep

## **4\. Implementation Principles**

### **4.1 Keep It Local**

Everything MUST run locally with ordinary filesystem operations.

### **4.2 Keep It Deterministic**

The checker and reconciler MUST behave deterministically against the frozen fixtures.

### **4.3 Keep It Small**

The implementation MUST solve only the mini contract, not a broader abstraction.

### **4.4 Keep It Consequence-Bearing**

The checker MUST exit nonzero when any BLOCK clause fails so CI can block merge.

### **4.5 Keep It Readable**

All filenames, fixture names, and sample contents MUST remain plain English, except for compact clause IDs.

## **5\. Required Deliverables**

The implementation is complete only when all of the following exist and work together:

* `src/reconcile.py`

* `src/check_contract.py`

* `contract/manifest.yaml`

* all required fixture directories and files

* `.github/workflows/ci.yaml`

* a passing pull-request gate for conformant changes

* a failing pull-request gate for non-conformant changes

## **6\. Reconciler Requirements**

## **6.1 Entry Point**

The reconciler MUST be invokable as:

python src/reconcile.py

It MUST also support:

python src/reconcile.py \--mode normal  
python src/reconcile.py \--mode reset

If no mode is provided, default behavior SHOULD be equivalent to `--mode normal`.

## **6.2 Input**

The reconciler MUST read desired state from:

`input/desired_state.json`

The input format is:

{  
 "items": \[  
   {  
     "unit\_id": "alpha",  
     "content": "Updated generated content"  
   }  
 \]  
}

## **6.3 Output**

For each desired item, the reconciler MUST materialize:

* `out/<unit_id>/doc.txt`

* `out/<unit_id>/meta.json`

`doc.txt` MUST contain the exact desired content.

`meta.json` MUST contain exactly:

* `schema_version`

* `unit_id`

with:

* `schema_version` \= `"0.2"`

## **6.4 Managed Scope**

The reconciler manages only:

* `doc.txt`

* `meta.json`

It MUST treat every other file inside a unit directory as manual.

For the fixtures, the canonical manual file is:

* `manual.txt`

## **6.5 Normal Mode Behavior**

In normal mode, the reconciler MUST:

* create missing desired unit directories

* create or update managed files for desired units

* preserve `manual.txt` when updating an existing desired unit

* detect stale unit directories

* fail if stale units exist while deletions are disabled

* remove only managed files from stale units when deletions are enabled

* preserve `manual.txt` in stale units

* preserve a stale unit directory if it remains non-empty after managed-file removal

## **6.6 Reset Mode Behavior**

In reset mode, the reconciler MUST still preserve `manual.txt`.

Reset mode exists specifically to exercise the directory-mutating surface that is most likely to drift into whole-directory replacement.

Reset mode MAY rebuild managed files more aggressively than normal mode, but it MUST NOT destroy `manual.txt`.

## **6.7 Deletion Policy**

The reconciler MUST use:

`MINI_RECONCILER_ALLOW_DELETIONS`

Rules:

* `"true"` enables stale-unit deletion behavior

* any other value, including unset, disables deletions

If deletions are disabled and a stale unit exists, the reconciler MUST:

* exit with code `1`

* leave `out/` unchanged

## **6.8 Failure Behavior**

If a run fails, the reconciler MUST NOT partially mutate managed state in a way that breaks fixture expectations.

For v0, “good enough” behavior is:

* either the expected final state is produced

* or the fixture remains unchanged when failure is expected

The implementation does not need a sophisticated transaction engine.  
 It only needs to satisfy the frozen fixtures.

## **7\. Checker Requirements**

## **7.1 Entry Point**

The checker MUST be invokable as:

python src/check\_contract.py

## **7.2 Checker Inputs**

The checker MUST read:

* `contract/manifest.yaml`

* the referenced fixture directories

* `src/reconcile.py`

## **7.3 Checker Responsibilities**

The checker MUST:

* load the manifest

* validate the manifest

* locate referenced fixtures

* execute each fixture in an isolated temporary workspace

* compare actual results to expected results

* evaluate clause outcomes

* compute aggregate clause outcomes

* print a readable summary

* write a JSON summary

* exit nonzero if any BLOCK clause fails

## **7.4 Fixture Execution Protocol**

For each fixture, the checker MUST:

1. create a temporary workspace

2. create `input/` and `out/`

3. copy fixture `desired_state.json` to `input/desired_state.json`

4. copy fixture `initial_out/` to `out/`

5. apply fixture environment variables

6. run `python src/reconcile.py <run_args...>`

7. capture exit code

8. compare actual `out/` to `expected_out/`

9. mark the fixture pass or fail

## **7.5 Comparison Rules**

Directory comparison MUST be exact:

* same paths

* same filenames

* same file contents

For v0, exact comparison is sufficient.

## **7.6 Clause Mapping**

The checker MUST support these direct clause mappings:

* `MC-DEL-1` → `delete_preserves_manual_file`

* `MC-OVR-1` → `overwrite_preserves_manual_file`

* `MC-RST-1` → `reset_preserves_manual_file`

* `MC-POL-1` → `stale_unit_blocked_when_deletions_disabled`

The checker MUST compute:

* `MC-GLOB-1`

`MC-GLOB-1` passes only if:

* `MC-DEL-1` passes

* `MC-OVR-1` passes

* `MC-RST-1` passes

## **7.7 Checker Outputs**

The checker MUST print a readable summary like:

Mini Contract Check Results

PASS  MC-DEL-1  delete\_preserves\_manual\_file  
PASS  MC-OVR-1  overwrite\_preserves\_manual\_file  
PASS  MC-RST-1  reset\_preserves\_manual\_file  
PASS  MC-POL-1  stale\_unit\_blocked\_when\_deletions\_disabled  
PASS  MC-GLOB-1 aggregate

The checker MUST also write:

`artifacts/check_contract_summary.json`

## **7.8 Exit Behavior**

The checker MUST exit with:

* `0` if all evaluated BLOCK clauses pass

* `1` if any evaluated BLOCK clause fails

This rule is what makes the checker usable as a CI gate.

## **8\. Fixture Implementation Requirements**

The repo MUST include these four frozen fixtures:

* `delete_preserves_manual_file`

* `overwrite_preserves_manual_file`

* `reset_preserves_manual_file`

* `stale_unit_blocked_when_deletions_disabled`

Each fixture directory MUST contain:

* `desired_state.json`

* `initial_out/`

* `expected_out/`

* `expected_result.json`

Fixture contents MUST match the frozen fixture package specification.

## **9\. CI Requirements**

## **9.1 Trigger**

The CI workflow MUST run on pull requests to the default branch.

For v0, it SHOULD run on all pull requests rather than using path filters.

## **9.2 Gate Behavior**

The workflow MUST run:

python src/check\_contract.py

If the checker exits nonzero, the workflow MUST fail.

## **9.3 Merge Behavior**

The contract-check workflow SHOULD be configured as a required status check for merge.

That is the point where the mini contract becomes consequence-bearing.

## **10\. Build Order**

## **Phase 1 — Seed the Repo**

Create:

* repo skeleton

* `contract/` directory

* `fixtures/` directory

* `src/` directory

* `artifacts/.gitkeep`

Acceptance condition:

* repo structure exists exactly as planned

## **Phase 2 — Freeze Contract Artifacts**

Add:

* `contract/contract-v0.2.md`

* `contract/fixture-package-spec-v0.1.md`

* `contract/checker-spec-v0.1.md`

* `contract/implementation-plan-v0.1.md`

* `contract/manifest.yaml`

Acceptance condition:

* all source authority artifacts exist in versioned filenames

## **Phase 3 — Install Fixtures**

Create all four fixture directories with frozen contents.

Acceptance condition:

* fixtures exist with correct names, shapes, and file contents

## **Phase 4 — Implement the Reconciler**

Implement `src/reconcile.py` with only the behavior needed to satisfy the frozen fixtures.

Recommended internal responsibilities:

* load desired state

* identify desired units

* write managed files for desired units

* preserve `manual.txt` on overwrite

* handle stale units according to deletion flag

* preserve `manual.txt` on delete

* support reset mode without destroying `manual.txt`

Acceptance condition:

* the reconciler can be run manually against fixture states and behaves as expected

## **Phase 5 — Implement the Checker**

Implement `src/check_contract.py`.

Recommended internal split:

* `load_manifest()`

* `validate_manifest()`

* `run_fixture()`

* `compare_output_tree()`

* `evaluate_direct_clauses()`

* `evaluate_aggregate_clauses()`

* `print_summary()`

* `write_summary()`

Acceptance condition:

* checker runs all referenced fixtures

* checker computes clause results

* checker emits readable summary

* checker exits correctly

## **Phase 6 — Add GitHub Actions**

Create `.github/workflows/ci.yaml`.

The workflow SHOULD:

* check out the repo

* set up Python

* run `python src/check_contract.py`

Acceptance condition:

* a passing repo state produces a green workflow

* a broken invariant produces a red workflow

## **Phase 7 — Prove the Gate**

Open or simulate at least two classes of changes:

### **Passing change**

A change that keeps:

* delete preservation

* overwrite preservation

* reset preservation

* deletion policy behavior

Expected result:

* CI passes

### **Failing change**

A change that destroys `manual.txt` on one required surface, such as reset or overwrite

Expected result:

* the directly bound clause fails

* `MC-GLOB-1` fails

* CI fails

Acceptance condition:

* the repo demonstrates both conformant and non-conformant PR outcomes

## **11\. Suggested First-Cut Implementation Strategy**

To keep the first pass small:

### **Reconciler**

Use ordinary Python filesystem operations only.

No framework.  
 No classes unless they make the code simpler.  
 No generalized plugin model.

### **Checker**

Use:

* `json`

* `yaml`

* `pathlib`

* `shutil`

* `subprocess`

* `tempfile`

That is enough.

### **CI**

Use one simple workflow.  
 Do not optimize for speed or matrix builds yet.

## **12\. Done Condition**

This implementation plan is complete when all of the following are true:

* the mini contract exists in the repo

* the fixture package exists in the repo

* the manifest binds clauses to fixtures

* the reconciler satisfies the frozen fixtures

* the checker evaluates the fixtures and clause outcomes

* the CI workflow fails on BLOCK violations

* the repo can visibly distinguish a conformant change from a non-conformant one

## **13\. Non-Goals**

This implementation plan does not attempt to deliver:

* generalized external authority infrastructure

* reusable framework code

* automatic contract extraction

* full policy engine semantics

* broad static analysis

* anything beyond the smallest working gate that proves the concept

