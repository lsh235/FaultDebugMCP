# Integrated report event limit: feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.13` candidate.

## Decision

**YES — expose the existing bounded report event limit in the integrated
workflow.** This removes a second-command step for users who need to tune
incident context, while preserving alpha12's output by default and reusing the
existing writer contract.

## Conditions for acceptance

1. Add `--fault-report-max-events` with the same inclusive 1–500 range as the
   standalone report command; default to 80.
2. Require `--fault-report` and reject malformed values before build
   preparation, so invalid input cannot configure or execute a project.
3. Forward the option to the existing verified-bundle report writer. Keep
   capture bytes, omitted-event accounting, target/report statuses, and
   collision protection unchanged.
4. Cover CLI rejection, direct report truncation/accounting, and installed
   adoption behavior for an explicit small value and the unchanged default.

See the [research record](integration-report-event-limit-research.md).
