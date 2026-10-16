# Integrated report output path: feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.14` candidate.

## Decision

**YES — expose the report writer's output path in the integrated flow.** This
lets automation separate captures from their readable documents without
rerunning a second command. The default stays beside the capture, and the
existing verified-bundle writer remains the only publisher.

## Conditions for acceptance

1. Add `--fault-report-output PATH`, requiring `--fault-report`; keep the
   existing adjacent report directory as the default.
2. Reject a destination that already exists or is a symlink before build
   preparation, including a broken symlink. Recheck immediately before atomic
   publication to handle a destination created during target execution.
3. Let the existing writer create missing parents and publish the three report
   documents together. Return its resolved path in the execution JSON.
4. Test paths with spaces, missing parents, collisions, CLI option dependency,
   unchanged target/report status semantics, and installed normal/fatal
   adoption behavior.

See the [research record](integration-report-output-research.md).
