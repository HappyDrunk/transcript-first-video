# scripts/

Deterministic worker CLIs live in the host project (enqueue job, process `--limit 1`, refresh media URL).

This skill folder intentionally ships policy + pitfalls + evals first. When you extract a standalone minipackage, place the runnable entrypoints here (or link to them) so agents do not reinvent the wheel each run.
