# **Mini Reconciler Convergence Contract v0.2**

Version 0.2

## **1\. Purpose**

This contract defines a minimal local filesystem reconciler whose purpose is to demonstrate contract-bound CI gating.

The system exists to prove one governing rule:

Manual files inside managed unit directories MUST be preserved under every directory-mutating operation.

This contract is intentionally narrow. It is not a general synchronization framework.

## **2\. Definitions**

### **2.1 Desired State**

The canonical input file describing which units should exist.

### **2.2 Unit ID**

Stable identifier for one desired unit.

### **2.3 Unit Directory**

Repository path:

out/\<unit\_id\>/

### **2.4 Managed Files**

The reconciler manages only:

* doc.txt

* meta.json

### **2.5 Manual File**

Any file inside a Unit Directory other than doc.txt or meta.json.

For the fixture suite, the canonical manual file is:

* manual.txt

### **2.6 Stale Unit**

A Unit Directory present under out/ whose unit\_id is absent from Desired State.

### **2.7 Directory-Mutating Operation**

Any operation that can add, remove, replace, reset, or clean contents of a Unit Directory.

For this contract, the required mutation surfaces are:

* delete

* overwrite

* reset

## **3\. Input Model**

### **3.1 Canonical Input**

Desired State MUST be read from:

input/desired\_state.json

### **3.2 Desired Item Shape**

Each desired item MUST contain:

* unit\_id

* content

### **3.3 Identity**

unit\_id is canonical identity.

unit\_id values MUST be unique within Desired State.

If duplicate unit\_id values exist, the run MUST fail.

## **4\. Output Model**

### **4.1 Output Layout**

For each desired item, the reconciler MUST materialize:

* out/\<unit\_id\>/doc.txt

* out/\<unit\_id\>/meta.json

### **4.2 doc.txt**

doc.txt MUST contain exactly the content value from Desired State for that unit.

### **4.3 meta.json**

meta.json MUST contain exactly:

* schema\_version

* unit\_id

Additional fields are prohibited unless introduced by a future contract version.

schema\_version MUST be:

“0.2”

## **5\. Ownership Boundary**

### **5.1 Managed Scope**

The reconciler manages only these paths within each Unit Directory:

* doc.txt

* meta.json

### **5.2 Manual Scope**

The reconciler MUST treat every other path within a Unit Directory as manual.

### **5.3 Preservation Rule**

The reconciler MUST NOT delete, overwrite, rename, or modify a Manual File unless a future contract version explicitly authorizes it.

### **5.4 Root Scope**

The reconciler manages only paths under out/.

It MUST NOT modify files outside out/.

## **6\. Convergence Semantics**

### **6.1 Convergence Target**

After a successful run:

* every desired unit MUST exist

* every managed file MUST match Desired State

* stale units MUST be handled according to deletion policy

* manual files MUST be preserved

### **6.2 Overwrite / Re-Export**

When an existing desired unit is re-exported, the reconciler MAY replace managed files but MUST preserve all Manual Files in that Unit Directory.

### **6.3 Stale Deletion**

If deletions are enabled and a stale unit contains Manual Files, the reconciler MAY remove only managed files.

If Manual Files remain, the Unit Directory MUST be preserved.

### **6.4 Empty Stale Directory**

If a stale unit contains no Manual Files after managed-file removal, the reconciler MAY remove the empty directory.

### **6.5 Reset / Cleanup**

Any reset, cleanup, or recreate logic affecting a Unit Directory MUST preserve Manual Files.

## **7\. Deletion Policy**

### **7.1 Control Surface**

Deletions are controlled only by:

MINI\_RECONCILER\_ALLOW\_DELETIONS

### **7.2 Allowed Values**

* “true” enables stale deletion behavior

* any other value, including unset, disables deletions

### **7.3 Disabled Deletions**

If deletions are disabled and any stale unit exists, the run MUST fail with exit code 1\.

Silent success is prohibited.

## **8\. Atomicity**

### **8.1 Atomic Apply**

Managed-state updates MUST be atomic.

### **8.2 No Partial Commit**

If a run fails, no partial managed state may be committed.

### **8.3 Preservation During Apply**

Atomic apply logic MUST preserve Manual Files.

A whole-directory replacement that destroys Manual Files is prohibited.

## **9\. Global Invariant**

### **9.1 Manual File Preservation**

Manual Files inside Unit Directories MUST be preserved under all directory-mutating operations.

### **9.2 Required Surfaces**

This invariant applies at minimum to:

* stale deletion

* overwrite / re-export

* reset / cleanup

### **9.3 Incomplete Surface Coverage**

An implementation that preserves Manual Files on one required surface but destroys them on another is non-conformant.

## **10\. Failure Model**

The run MUST fail with exit code 1 if any of the following occur:

* invalid input shape

* duplicate unit\_id

* stale units exist while deletions are disabled

* a Manual File would be destroyed

* partial managed state would be committed

* fixture output does not match expected result

On failure:

* no deletions may occur

* no Manual Files may be lost

* previous valid managed state MUST remain intact

## **11\. CI Requirements**

### **11.1 Required Gate**

CI MUST run contract-bound checks and MUST fail on any BLOCK violation.

### **11.2 Deletion Safety**

Normal CI runs MUST execute with deletions disabled.

CI MUST NOT set MINI\_RECONCILER\_ALLOW\_DELETIONS=true except in a deletion-specific test job.

### **11.3 Global Invariant Gate**

CI MUST fail if Manual File preservation does not hold across all required mutation surfaces.

## **12\. Fixture Requirements**

Fixtures MUST exist under fixtures/.

Each fixture MUST include:

* desired\_state.json

* initial\_out/

* expected\_out/

* expected\_result.json

## **13\. Required Fixtures**

### **13.1 Delete Preserves Manual**

A stale unit contains doc.txt, meta.json, and manual.txt.

When deletions are enabled, managed files may be removed but manual.txt MUST remain.

### **13.2 Overwrite Preserves Manual**

An existing desired unit is re-exported.

Managed files change.

manual.txt MUST remain unchanged.

### **13.3 Reset Preserves Manual**

A reset or cleanup path is exercised.

manual.txt MUST remain unchanged.

### **13.4 Stale Blocked When Deletions Disabled**

A stale unit exists while deletions are disabled.

The run MUST fail with exit code 1\.

## **14\. Non-Goals**

This contract does not attempt to define:

* general document synchronization

* remote APIs

* Google Docs behavior

* rich rendering

* runtime natural-language interpretation

* manual merging into managed files

* generalized authority infrastructure

* full formal verification

