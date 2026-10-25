# SSR/ASR release evidence family identity safety

## Scope

The read-only `/demo/releases` response can contain several synthetic SSR and ASR release rows. The backend stores Snapshot IDs as primary keys and requires `snapshot_no`, `approval_no`, and `decision_no` to be globally unique. Each of those identities therefore belongs to one release evidence family.

The shared runtime parser now requires every initialized demonstration response to keep these non-null identities distinct across release rows:

- current Snapshot `id`;
- current Snapshot `snapshot_no`;
- Approval `approval_no`;
- Release Decision `decision_no`.

If any identity appears in two rows, the complete demonstration response is rejected. The page uses the existing evidence-unavailable state, renders neither conflicting family, and does not infer a formal release.

## Preserved behavior

- A row without a current Snapshot, Approval, or Decision does not reserve a missing identity.
- A Decision may still explicitly report evidence that is not bound to the current Snapshot; the existing binding checks and visible warning remain responsible for that within-row state.
- Distinct releases may retain the same DVP identity because every DVP link carries its own release and Snapshot query context.
- The existing release-row identity, row-local DVP identity, rule identity, text, hash, count, binding, initialization, and confirmation checks remain unchanged.

## Safety boundary

This is client-side validation of one bounded synthetic response. It does not establish database authenticity, real identity, approval authority, deployment, or production release. Public and demonstration environments remain read-only.

## Verification

`frontend/tests/release-demo-evidence.test.cjs` covers duplicate Snapshot IDs, Snapshot numbers, Approval numbers, and Decision numbers. Each conflict must make the complete response unavailable. A positive case proves that two otherwise distinct evidence families may still reuse the same DVP identity under separate release and Snapshot contexts.
