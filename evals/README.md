# Local evaluations

The release evaluation path is `uv run causalgate benchmark`. It executes 32 labeled synthetic variants across eight rules and checks reproducibility. Behavior is graded by rule presence, evidence integrity, clean target-rule near-misses, and stable fixture hashes, never by volatile run identifiers or prose.

`corpus-manifest.json` defines evidence scope, label method, reported metrics, and locked-test requirements. The benchmark reports confusion counts, specificity, per-rule results, and two-sided 95% Wilson intervals in addition to point estimates.

These cases are synthetic regression evidence, not independent scientific validation. Claims beyond the bundled fixture scope require the locked, independently annotated corpus described in `docs/ASSURANCE-SPEC.md`.
