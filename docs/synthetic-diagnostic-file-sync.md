# Synthetic diagnostic-copy final-sync evidence

This test-only adapter operates exclusively on pytest-owned temporary directories
and two synthetic members. It is not a production archive, receiver, retention
interface or restore command. It assumes exclusive fixture ownership; concurrent
or hostile path replacement is not modeled. No operational location, role,
retention duration or real-data inclusion is selected.

The fixture independently records expected names, lengths and SHA-256 before the
copy. It reuses the PR269 bounded member contract, preserving the original
RECONCILIATION_REQUIRED observation and null stored_receipt. PR268's real-worker
and committed-restore rejection regression remains unchanged.

The adapter creates an absent destination exclusively, writes and syncs each member,
closes it, independently reads it back, syncs the destination directory, creates and
syncs an empty test completion marker, syncs the marked directory, and finally
syncs its parent. This ordering borrows only the stage distinction from
scripts/offline_media_transport.py; it does not reuse its archive format or alter
that production script. Every error propagates and only owned descriptors close.
There is no retry, overwrite, removal or evidence repair.

A one-shot EIO hook targets final_parent by stage and the owned parent's device/inode,
not a global fsync count. It verifies both members and marker are already visible.
A second invocation would succeed, so an accidental retry can hide the first error.
The regression requires exactly one final-parent call and the original exception,
with no successful call receipt. An in-memory retry mutation is rejected by the
regression (DID NOT RAISE OSError), proving it detects that masking behavior.

Controls cover no fault and failure before marker creation. Snapshots show source
and target bytes, inode, mode, size and mtime remain unchanged during subsequent
readback (atime is intentionally excluded). The marker is absent in the early
failure case and present in the final-sync failure case. A new readback may confirm
only current member equality; it neither emits a copy-call receipt nor changes the
recorded failure. Successful sync calls also do not prove power-loss durability.
No crash, actual backup/restore, database, deployment or company environment is used.

Initial collection failed because the new adapter did not yet exist. The three
new cases and unchanged contract/restore cases passed25 locally. Broader related suite:149passed/no skips,18.86s. Independent-review/CI evidence
is recorded in the PR. Business acceptance stays
36/44 (82%), increment0. Next operational gate remains trusted inventory custody
and an explicitly chosen retention lifecycle, followed by environment-specific
verification; these synthetic files do not establish those guarantees.
