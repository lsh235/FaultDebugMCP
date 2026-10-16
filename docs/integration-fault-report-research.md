# First-capture report handoff: research

Date: 2026-10-17 (Asia/Seoul). Candidate: v1.3.0-alpha.11.
Baseline: v1.3.0-alpha.10 at `a423fc4fadb7b9868f614954797aa27cdd486467`.

## User friction

`faultdebug integrate --execute-target` now builds, runs, and validates one
capture, but the user must still copy the artifact path and verified bundle
path into a second `faultdebug fault-report` command. That is a small but
avoidable handoff in the first-install workflow.

## Existing behavior checked

- `execute_integration_target` returns the artifact path only after
  `collect_file` validates the single `.fault` and computes completeness,
  stability, event and loss counts (`faultdebug/adoption.py`).
- The integration build result carries the verified source bundle path.
- `write_fault_report` re-reads and checksum-validates the same artifact bytes,
  verifies the supplied source bundle, writes JSON/Markdown/HTML into a new
  directory, and refuses an existing output (`faultdebug/fault_report.py`).
- A generated checksummed capture with no crash record successfully produced a
  complete report from a verified bundle in an isolated temporary directory.
  The report says “장애 레코드 없음” and keeps crash count at zero; it does not
  invent a fault. Thus this handoff also covers normal smoke captures.
- A nonzero target can still produce a valid `.fault`; alpha10 deliberately
  keeps target status `FAIL` while returning that validated artifact path.

## Options

1. Keep the second manual command. This preserves current behavior but retains
   path-copying friction after the first capture.
2. Always generate reports after target execution. Rejected because an implicit
   write changes the opt-in contract and may collide with existing user data.
3. Add an explicit `--fault-report` opt-in. On a target result with one already
   validated artifact, write the existing report next to it as
   `<artifact-stem>-report/`, using the build's verified bundle. Refuse an
   existing or symlinked destination. Report generation has its own status;
   it cannot turn a failed target into a successful execution. Accepted for
   review.

The generated directory is deterministic because the target artifact
directory must be empty before launch. A normal capture may produce a report
with no crash section entries; a failed target may still produce a useful
report if its validated capture is available. No root cause is inferred.

## Proposed acceptance

- Plan-only and build-only remain unchanged and never write a report.
- `--fault-report` requires explicit `--execute-target` (which itself requires
  `--execute-build`).
- A verified normal capture produces the three existing report files, bound to
  the exact capture checksum and verified bundle.
- A nonzero target with a valid capture still gets a report, while target and
  overall execution remain failed.
- Missing/invalid captures, invalid bundles, existing outputs and symlinks fail
  closed without replacing files or reporting a successful report.
- The report stays evidence-bound: no-crash captures remain no-crash, source
  text comes only from the verified bundle, and report errors remain distinct
  from target errors.

No external-project completion is claimed by this candidate. The two pinned
upstream source trees remain unavailable in the current acceptance inputs.
