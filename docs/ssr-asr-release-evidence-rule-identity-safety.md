# SSR/ASR release evidence rule-identity safety

The SSR/ASR evidence views treat a readiness rule's `group` and `rule` fields together as its identity. A summary or demonstration response must not contain the same identity more than once.

The shared frontend parser rejects the complete affected response when a duplicate identity is present. This prevents two rows for one rule from presenting conflicting effective statuses or evidence while the surrounding snapshot, readiness, approval, decision, and `current_release_confirmed` fields claim a formal release. The existing unavailable state is rendered instead; no partial rule list is trusted.

A rule label may still be reused in a different group. Both read-only views use the same composite identity for React row keys, matching the parser contract without treating the label alone as globally unique.

This package changes only read-only SSR/ASR interpretation, rendering identity, and regression coverage. It does not change backend rule calculation, database state, migrations, Seed data, dependencies, authentication, write gates, CI, or deployment configuration.
