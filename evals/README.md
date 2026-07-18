# Local evaluations

The release evaluation path is `uv run agentflight benchmark`. It executes 32 labeled synthetic variants across eight rules and checks reproducibility. Behavior is graded by rule presence, evidence integrity, clean protected near-misses, and identical fixture hashes, never by volatile run identifiers or prose.

