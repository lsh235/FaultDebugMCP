# Integrated report output path: research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.14`.
Baseline: `v1.3.0-alpha.13` at `59ee1671593f5f7025b7b55627d4b4097a912408`.

## User friction

`faultdebug integrate --fault-report` currently writes the report folder beside
the validated `.fault` artifact. The standalone `faultdebug fault-report`
command already accepts a required `--output` path, but the integrated flow
does not expose it. CI and incident scripts that keep captures in a build
artifact directory must either leave reports there or invoke a second command
to place reports in their chosen archive.

The existing report writer creates the requested report directory atomically,
creates missing parent directories, and refuses an existing or symlinked
destination. The integrated helper already separates target/report status and
uses the exact validated artifact and verified source bundle.

## Options

1. Keep the report beside the capture and require users to move it or rerun the
   standalone command. Rejected because the standalone output contract already
   exists and the integrated path has the exact artifact/bundle needed.
2. Always create the chosen directory, replacing files if it exists. Rejected:
   this risks overwriting prior incident evidence.
3. Add `--fault-report-output PATH`, valid only with `--fault-report`. Preserve
   the adjacent-directory default; require a new destination, reject existing
   files/directories/symlinks before project preparation, and retain the
   writer's final atomic collision check. Accepted for review.

A relative path is interpreted from the caller's current working directory.
The user-selected parent path may be created, while the report directory
itself must be new. The location does not change capture identity, source
verification, event limit, language, or target/report/overall status rules.

## Proposed acceptance

- No option preserves alpha13's report-beside-capture location.
- An explicit path receives the same verified JSON/Markdown/HTML report,
  including when the directory has spaces or missing parent components.
- Existing, regular-file, and symlink destinations are rejected before
  project preparation; the final writer still handles a concurrent collision.
- The option without `--fault-report` is rejected before project access.
- Installed adoption acceptance checks the custom normal-report location and
  the unchanged default location for a fatal target; source and original build
  inputs remain unchanged.
