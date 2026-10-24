# SSR/ASR release evidence coverage-count safety

The SSR/ASR evidence views treat DVP coverage counts as an ordered relationship, not as independent non-negative values:

`current_snapshot_passed <= current_snapshot_executed <= required_dvp_total`

The shared frontend parser now rejects a summary or demonstration response when either relationship is violated. The affected evidence is rendered as unavailable, so impossible counts cannot support a formal-release statement even if readiness, approval, decision, Snapshot binding, and `current_release_confirmed` otherwise claim success.

Zero required, executed, and passed items remain a structurally valid count set. Existing readiness rules still decide whether that evidence can confirm a release. The change does not infer missing executions, clamp values, rewrite evidence, or add any request.

This package changes only the read-only SSR/ASR interpretation and its regression coverage. It does not change backend calculations, database state, migrations, Seed data, dependencies, authentication, write gates, CI, or deployment configuration.
