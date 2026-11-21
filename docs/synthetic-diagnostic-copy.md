# Synthetic diagnostic-copy completion contract

This is a test-only in-memory model, not an archive format, retention interface,
restorer or operator instruction. It does not add a production caller or path input.

PR268 already proves that actual synthetic bytes can coexist with
RECONCILIATION_REQUIRED and no stored receipt, and that committed-only restore
acceptance refuses those facts without changing them. That regression is reused
unchanged. This model adds a separate question: did the declared diagnostic copy
retain all of its two synthetic members without changing their meaning?

The trusted fixture obtains an immutable expected name/size/SHA-256 list from its
own source before the writer operates. It is not inferred from the destination or
supplied as proof by an untrusted writer. A separately invoked verifier reads the
retained bytes in memory and checks the exact closed member set, bounded sizes and
all digests. Completion also requires the fixture's writer-completion condition.
That condition alone is insufficient. Missing members, changed bytes/lengths,
hashes without bytes, metadata alone, extra members and incomplete writes refuse
completion. A matching digest cannot authorize promoting the original state or
adding a success receipt. The exact synthetic observation remains
RECONCILIATION_REQUIRED with a null stored_receipt.

The result says only synthetic_copy_complete. Attachment commitment,
distribution, bootable backup and durability remain false. These fixtures are
not actual retained files, independent administrative custody or an atomic DB/media
snapshot. A hash proves equality to the independently held fixture expectation,
not provenance, authenticity or complete real-world scope. The model has no raw
exception output, paths, user identity, live database or real attachment content.
It neither retries, repairs nor deletes source evidence.

## Still unadopted operational decisions

- Whether real retention includes only observations or the underlying bytes.
- The destination and its independent write/read completion guarantees.
- Authorized readers, confidentiality controls and inclusion of real data.
- Retention duration and eventual disposition under an approved policy.
- Trustworthy acquisition of a complete expected inventory and its custody.

No real location, role, duration or access configuration is selected here. An
operational implementation requires those decisions and independent verification;
two temporary directories would not establish power-loss durability either.

Initial tests failed collection because the new contract did not exist. Related
local tests then passed146 with no skips (25.50s); exact-head normal CI belongs to the PR.
This is not evidence of real backup, restore, deployment or company acceptance.
Business acceptance remains36/44 (82%), increment0.
