# **Mini Reconciler Checker Specification v0.1**

**Version 0.1**

## **1\. Purpose**

This specification defines the behavior of the contract checker for the Mini Reconciler repo.

The checker exists to evaluate the repository against the Mini Contract by running deterministic fixture-based checks and reporting pass/fail results by clause ID.

The checker is a gate, not an interpreter of general prose.

## **2\. Checker Entry Point**

The checker MUST be invokable as:

python src/check\_contract.py

The checker MAY later accept optional flags, but v0 does not require them.

## **3\. Inputs**

The checker MUST read:

* `contract/manifest.yaml`

* fixture directories under `fixtures/`

* the reconciler entry point at:

  * `src/reconcile.py`

The checker MUST treat the manifest as the source of truth for:

* clause IDs

* fixture bindings

* aggregate clause requirements

* fail-on-BLOCK policy

## **4\. Required Checker Responsibilities**

The checker MUST:

* load and validate `contract/manifest.yaml`

* discover the fixtures referenced by the manifest

* execute each fixture in isolation

* compare actual results against expected results

* record pass/fail per bound clause

* compute aggregate clause outcomes

* print a readable summary

* emit a machine-readable JSON summary

* exit nonzero if any BLOCK clause fails

## **5\. Execution Model**

## **5.1 Isolated Fixture Runs**

Each fixture MUST be executed in an isolated temporary workspace.

The checker MUST NOT run fixtures in-place against the repository working tree.

## **5.2 Workspace Preparation**

For each fixture, the checker MUST:

1. create a temporary workspace

2. create:

   * `input/`

   * `out/`

3. copy fixture `desired_state.json` to:

   * `input/desired_state.json`

4. copy fixture `initial_out/` to:

   * `out/`

## **5.3 Reconciler Execution**

The checker MUST execute the reconciler using:

python src/reconcile.py \<run\_args...\>

Where:

* `<run_args...>` come from the fixture’s `expected_result.json`

* environment variables come from the fixture’s `expected_result.json`

The checker MUST capture:

* process exit code

* stdout

* stderr

## **6\. Fixture Pass/Fail Rules**

A fixture MUST pass only if:

* actual exit code equals `expected_exit_code`

* actual `out/` exactly matches `expected_out/`

A fixture MUST fail if either condition does not hold.

## **6.1 Exact Filesystem Comparison**

Directory comparison MUST be exact:

* same paths

* same filenames

* same file contents

For v0, exact match is sufficient.  
 No fuzzy comparison is allowed.

## **6.2 Failure Diagnostics**

If a fixture fails, the checker MUST report at least:

* fixture name

* expected exit code

* actual exit code

* missing paths

* unexpected paths

* changed file paths

## **7\. Clause Evaluation Model**

## **7.1 Direct Clause Checks**

The checker MUST evaluate these direct clause bindings through fixtures:

* `MC-DEL-1` via `delete_preserves_manual_file`

* `MC-OVR-1` via `overwrite_preserves_manual_file`

* `MC-RST-1` via `reset_preserves_manual_file`

* `MC-POL-1` via `stale_unit_blocked_when_deletions_disabled`

## **7.2 Aggregate Clause**

The checker MUST compute:

* `MC-GLOB-1`

`MC-GLOB-1` MUST pass only if all of the following pass:

* `MC-DEL-1`

* `MC-OVR-1`

* `MC-RST-1`

If any required preservation clause fails, `MC-GLOB-1` MUST fail.

## **7.3 CI Policy Clauses**

For v0, the checker MAY support these as manifest-only policy checks:

* `MC-CI-1`

* `MC-CI-2`

But the minimum required checker implementation is fixture-first.  
 So these policy clauses MAY be deferred until after fixture execution works.

## **8\. Output Requirements**

## **8.1 Console Output**

The checker MUST print a readable clause summary.

Recommended shape:

Mini Contract Check Results

PASS  MC-DEL-1  delete\_preserves\_manual\_file  
PASS  MC-OVR-1  overwrite\_preserves\_manual\_file  
FAIL  MC-RST-1  reset\_preserves\_manual\_file  
PASS  MC-POL-1  stale\_unit\_blocked\_when\_deletions\_disabled  
FAIL  MC-GLOB-1 aggregate

Summary:  
5 clauses evaluated  
2 failed

The exact typography may vary, but:

* clause ID MUST be shown

* PASS/FAIL MUST be shown

* bound fixture or aggregate status MUST be shown

## **8.2 JSON Summary**

The checker MUST emit a JSON summary file.

Recommended location:

* `artifacts/check_contract_summary.json`

Recommended shape:

{  
 "contract\_id": "mini-reconciler-convergence",  
 "contract\_version": "0.2",  
 "manifest\_version": "0.2",  
 "overall\_result": "FAIL",  
 "fail\_on\_block": true,  
 "clauses": \[  
   {  
     "clause\_id": "MC-DEL-1",  
     "result": "PASS",  
     "source": "fixture",  
     "fixture": "delete\_preserves\_manual\_file"  
   },  
   {  
     "clause\_id": "MC-OVR-1",  
     "result": "PASS",  
     "source": "fixture",  
     "fixture": "overwrite\_preserves\_manual\_file"  
   },  
   {  
     "clause\_id": "MC-RST-1",  
     "result": "FAIL",  
     "source": "fixture",  
     "fixture": "reset\_preserves\_manual\_file"  
   },  
   {  
     "clause\_id": "MC-POL-1",  
     "result": "PASS",  
     "source": "fixture",  
     "fixture": "stale\_unit\_blocked\_when\_deletions\_disabled"  
   },  
   {  
     "clause\_id": "MC-GLOB-1",  
     "result": "FAIL",  
     "source": "aggregate",  
     "depends\_on": \["MC-DEL-1", "MC-OVR-1", "MC-RST-1"\]  
   }  
 \]  
}

For failed fixture-backed clauses, the summary SHOULD also include diagnostics such as:

* expected exit code

* actual exit code

* missing paths

* unexpected paths

* changed files

## **9\. Exit Behavior**

The checker MUST exit with code `1` if any BLOCK clause fails.

The checker MUST exit with code `0` only if all evaluated BLOCK clauses pass.

This is the rule that makes the checker usable as a CI gate.

## **10\. Fixture Discovery Rules**

The checker MUST discover fixtures by manifest reference, not by blindly executing every directory under `fixtures/`.

That means:

* if a fixture is referenced by the manifest, it MUST exist

* if a referenced fixture does not exist, the checker MUST fail

* unreferenced fixture directories MAY be ignored in v0

This prevents accidental fixture drift from silently becoming contract scope.

## **11\. Manifest Validation Rules**

Before running fixtures, the checker MUST validate that:

* manifest file exists

* contract file path is present

* clause IDs are unique

* fixture IDs are unique

* every referenced fixture exists

* every aggregate dependency refers to an existing clause

If manifest validation fails, the checker MUST fail immediately.

## **12\. Recommended Internal Structure**

The checker does not need to expose this externally, but this is a good internal split:

* `load_manifest()`

* `validate_manifest()`

* `run_fixture()`

* `compare_output_tree()`

* `evaluate_direct_clauses()`

* `evaluate_aggregate_clauses()`

* `write_summary()`

* `print_summary()`

That is enough structure without overengineering it.

## **13\. Non-Goals**

The checker does not need to:

* interpret raw contract prose at runtime

* generate new tests from natural language

* reason with an LLM

* infer missing clause bindings

* validate general software correctness

* act as a universal contract engine

