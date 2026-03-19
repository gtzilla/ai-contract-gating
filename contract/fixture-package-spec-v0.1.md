# **Mini Reconciler Fixture Package Specification v0.1**

**Version 0.1**

## **1\. Purpose**

This specification defines the fixture package for the Mini Reconciler Convergence Contract v0.2.

The fixture package exists to provide deterministic, local, contract-bound test cases for the CI gate.

The fixture package is intentionally narrow. Its purpose is not to test every possible reconciler behavior. Its purpose is to test the specific preserved truths bound by the mini contract.

## **2\. Naming Policy**

### **2.1 Human-Readable Names**

Fixture directory names MUST use plain English.

Examples:

* `delete_preserves_manual_file`

* `overwrite_preserves_manual_file`

* `reset_preserves_manual_file`

* `stale_unit_blocked_when_deletions_disabled`

### **2.2 Unit IDs**

Unit IDs in fixtures MUST use plain-English identifiers.

Examples:

* `alpha`

* `stale-alpha`

### **2.3 Clause IDs**

Clause IDs MAY remain short for tooling and CI output.

Examples:

* `MC-DEL-1`

* `MC-OVR-1`

* `MC-RST-1`

* `MC-POL-1`

* `MC-GLOB-1`

`MC` means **Mini Contract**.

## **3\. Required Fixture Directory Shape**

Each fixture directory MUST have exactly this shape:

fixtures/\<fixture\_name\>/  
 desired\_state.json  
 initial\_out/  
 expected\_out/  
 expected\_result.json

Each file has a fixed purpose:

* `desired_state.json` defines the desired units for the run

* `initial_out/` defines the pre-run filesystem state

* `expected_out/` defines the required post-run filesystem state

* `expected_result.json` defines the required process result and fixture metadata

## **4\. File Semantics**

## **4.1 desired\_state.json**

This file defines the desired-state input consumed by the reconciler.

The file MUST use this shape:

{  
 "items": \[  
   {  
     "unit\_id": "alpha",  
     "content": "Updated generated content"  
   }  
 \]  
}

Rules:

* top-level key MUST be `items`

* `items` MUST be an array

* each item MUST include:

  * `unit_id`

  * `content`

## **4.2 initial\_out/**

This directory represents the exact pre-run state of `out/`.

The fixture runner MUST copy `initial_out/` to the temporary runtime `out/` before executing the reconciler.

## **4.3 expected\_out/**

This directory represents the exact required post-run state of `out/`.

The fixture runner MUST compare actual `out/` against `expected_out/`.

Comparison MUST be exact:

* same paths

* same filenames

* same file contents

## **4.4 expected\_result.json**

This file defines the expected process result and fixture metadata.

It MUST use this shape:

| { "expected\_exit\_code": 0, "run\_args": \["--mode", "normal"\], "env": {}, "covers\_clauses": \["MC-DEL-1", "MC-GLOB-1"\], "notes": "Managed files may be removed from a stale unit, but manual.txt must remain."} |
| :---- |

Field meanings:

* `expected_exit_code`: required process exit code

* `run_args`: exact CLI arguments for the reconciler

* `env`: environment variables required for the run

* `covers_clauses`: clause IDs this fixture is intended to prove

* `notes`: human-readable explanation

## **5\. Canonical Runtime Model**

The fixture runner MUST execute each fixture in an isolated temporary workspace.

The execution protocol MUST be:

1. Create a temporary workspace.

2. Copy fixture `desired_state.json` to:

   * `input/desired_state.json`

3. Copy fixture `initial_out/` to:

   * `out/`

4. Apply environment variables from `expected_result.json`.

5. Execute:

python src/reconcile.py \<run\_args...\>

6. Capture the process exit code.

7. Compare actual `out/` against `expected_out/`.

8. Compare actual exit code against `expected_exit_code`.

9. Emit pass/fail results for the clauses covered by the fixture.

## **6\. Canonical Shared File Shapes**

## **6.1 Managed Files**

The reconciler manages only:

* `doc.txt`

* `meta.json`

## **6.2 Manual File**

The canonical manual file is:

* `manual.txt`

This file represents human-created content that MUST survive all required mutation surfaces.

## **6.3 meta.json**

All fixture `meta.json` files MUST use this shape:

| { "schema\_version": "0.2", "unit\_id": "alpha"} |
| :---- |

Rules:

* `schema_version` MUST be `"0.2"`

* `unit_id` MUST match the containing unit directory name

## **7\. Required Fixtures**

## **7.1 delete\_preserves\_manual\_file**

### **Purpose**

This fixture proves:

* `MC-DEL-1`

* part of `MC-GLOB-1`

A stale unit contains managed files plus `manual.txt`.

When deletions are enabled:

* managed files MAY be removed

* `manual.txt` MUST remain

* the directory MUST remain because it is not empty

### **Directory Shape**

| fixtures/delete\_preserves\_manual\_file/ desired\_state.json initial\_out/   stale-alpha/     doc.txt     meta.json     manual.txt expected\_out/   stale-alpha/     manual.txt expected\_result.json |
| :---- |

### **desired\_state.json**

| { "items": \[\]} |
| :---- |

### **initial\_out/stale-alpha/doc.txt**

Generated content for a stale unit

### **initial\_out/stale-alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "stale-alpha"} |
| :---- |

### **initial\_out/stale-alpha/manual.txt**

This file was added manually and must survive deletion.

### **expected\_out/stale-alpha/manual.txt**

This file was added manually and must survive deletion.

### **expected\_result.json**

| { "expected\_exit\_code": 0, "run\_args": \["--mode", "normal"\], "env": {   "MINI\_RECONCILER\_ALLOW\_DELETIONS": "true" }, "covers\_clauses": \["MC-DEL-1", "MC-GLOB-1"\], "notes": "Managed files may be removed from a stale unit, but manual.txt must remain."} |
| :---- |

## **7.2 overwrite\_preserves\_manual\_file**

### **Purpose**

This fixture proves:

* `MC-OVR-1`

* part of `MC-GLOB-1`

An existing desired unit is re-exported.

After the run:

* managed files MUST reflect desired state

* `manual.txt` MUST remain unchanged

### **Directory Shape**

| fixtures/overwrite\_preserves\_manual\_file/ desired\_state.json initial\_out/   alpha/     doc.txt     meta.json     manual.txt expected\_out/   alpha/     doc.txt     meta.json     manual.txt expected\_result.json |
| :---- |

### **desired\_state.json**

| { "items": \[   {     "unit\_id": "alpha",     "content": "Updated generated content"   } \]} |
| :---- |

### **initial\_out/alpha/doc.txt**

Original generated content

### **initial\_out/alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "alpha"} |
| :---- |

### **initial\_out/alpha/manual.txt**

This file was added manually and must survive overwrite.

### **expected\_out/alpha/doc.txt**

Updated generated content

### **expected\_out/alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "alpha"} |
| :---- |

### **expected\_out/alpha/manual.txt**

This file was added manually and must survive overwrite.

### **expected\_result.json**

| { "expected\_exit\_code": 0, "run\_args": \["--mode", "normal"\], "env": {}, "covers\_clauses": \["MC-OVR-1", "MC-GLOB-1"\], "notes": "Managed files are updated, but manual.txt must remain unchanged."} |
| :---- |

## **7.3 reset\_preserves\_manual\_file**

### **Purpose**

This fixture proves:

* `MC-RST-1`

* part of `MC-GLOB-1`

This fixture exists to catch whole-directory replacement or reset logic that destroys `manual.txt`.

### **Directory Shape**

| fixtures/reset\_preserves\_manual\_file/ desired\_state.json initial\_out/   alpha/     doc.txt     meta.json     manual.txt expected\_out/   alpha/     doc.txt     meta.json     manual.txt expected\_result.json |
| :---- |

### **desired\_state.json**

| { "items": \[   {     "unit\_id": "alpha",     "content": "Reset-mode generated content"   } \]} |
| :---- |

### **initial\_out/alpha/doc.txt**

Content before reset

### **initial\_out/alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "alpha"} |
| :---- |

### **initial\_out/alpha/manual.txt**

This file was added manually and must survive reset.

### **expected\_out/alpha/doc.txt**

Reset-mode generated content

### **expected\_out/alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "alpha"} |
| :---- |

### **expected\_out/alpha/manual.txt**

This file was added manually and must survive reset.

### **expected\_result.json**

| { "expected\_exit\_code": 0, "run\_args": \["--mode", "reset"\], "env": {}, "covers\_clauses": \["MC-RST-1", "MC-GLOB-1"\], "notes": "Reset logic must preserve manual.txt."} |
| :---- |

## **7.4 stale\_unit\_blocked\_when\_deletions\_disabled**

### **Purpose**

This fixture proves:

* `MC-POL-1`

A stale unit exists while deletions are disabled.

The run MUST:

* fail with exit code `1`

* leave `out/` unchanged

### **Directory Shape**

| fixtures/stale\_unit\_blocked\_when\_deletions\_disabled/ desired\_state.json initial\_out/   stale-alpha/     doc.txt     meta.json expected\_out/   stale-alpha/     doc.txt     meta.json expected\_result.json |
| :---- |

### **desired\_state.json**

| { "items": \[\]} |
| :---- |

### **initial\_out/stale-alpha/doc.txt**

Generated content for a stale unit

### **initial\_out/stale-alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "stale-alpha"} |
| :---- |

### **expected\_out/stale-alpha/doc.txt**

Generated content for a stale unit

### **expected\_out/stale-alpha/meta.json**

| { "schema\_version": "0.2", "unit\_id": "stale-alpha"} |
| :---- |

### **expected\_result.json**

| { "expected\_exit\_code": 1, "run\_args": \["--mode", "normal"\], "env": {}, "covers\_clauses": \["MC-POL-1"\], "notes": "A stale unit exists while deletions are disabled. The run must fail and out/ must remain unchanged."} |
| :---- |

## **8\. Full Frozen Fixture Tree**

| fixtures/ delete\_preserves\_manual\_file/   desired\_state.json   initial\_out/     stale-alpha/       doc.txt       meta.json       manual.txt   expected\_out/     stale-alpha/       manual.txt   expected\_result.json overwrite\_preserves\_manual\_file/   desired\_state.json   initial\_out/     alpha/       doc.txt       meta.json       manual.txt   expected\_out/     alpha/       doc.txt       meta.json       manual.txt   expected\_result.json reset\_preserves\_manual\_file/   desired\_state.json   initial\_out/     alpha/       doc.txt       meta.json       manual.txt   expected\_out/     alpha/       doc.txt       meta.json       manual.txt   expected\_result.json stale\_unit\_blocked\_when\_deletions\_disabled/   desired\_state.json   initial\_out/     stale-alpha/       doc.txt       meta.json   expected\_out/     stale-alpha/       doc.txt       meta.json   expected\_result.json |
| :---- |

## **9\. Pass/Fail Rules**

A fixture MUST pass only if:

* actual exit code equals `expected_exit_code`

* actual `out/` exactly matches `expected_out/`

A fixture MUST fail if either of those conditions is not met.

For clause reporting:

* `delete_preserves_manual_file` binds to `MC-DEL-1`

* `overwrite_preserves_manual_file` binds to `MC-OVR-1`

* `reset_preserves_manual_file` binds to `MC-RST-1`

* `stale_unit_blocked_when_deletions_disabled` binds to `MC-POL-1`

`MC-GLOB-1` MUST pass only if all three preservation fixtures pass:

* `delete_preserves_manual_file`

* `overwrite_preserves_manual_file`

* `reset_preserves_manual_file`

## **10\. Non-Goals**

This fixture package does not attempt to prove:

* generalized document synchronization

* remote integration behavior

* AI reasoning quality

* full program correctness

* broad contract completeness

* formal verification

