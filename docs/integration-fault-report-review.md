# First-capture report handoff: feature review

Date: 2026-10-17 (Asia/Seoul). Review target: v1.3.0-alpha.11 candidate.

## Review decision

**YES — implement the bounded opt-in handoff.**

The feature removes one path-copying step from the new user's first capture
workflow by connecting two already implemented and separately verified stages.
It does not introduce a new report format or claim that a trace proves a cause.
An experiment confirmed that the existing report writer handles a complete
capture with zero crashes and a verified source bundle without inventing a
fault.

## Conditions for acceptance

1. Keep plan-only and build-only behavior unchanged; reporting must be explicit.
2. Use only the exact artifact returned after alpha10's checksum validation and
   the verified bundle returned by its build stage. The report writer must
   verify both again.
3. Report and target statuses remain separate. In particular, a nonzero target
   may receive a report but must remain a failed target and failed integration.
4. Never overwrite an existing or symlinked report destination. If no verified
   artifact exists, report `NOT RUN`; report generation errors are `FAIL`.
5. Confirm the real hosted Clang 18 adoption path produces a readable report
   for both a normal capture and a fatal capture; the fatal target and overall
   run must remain failed while its report resolves source only through the
   verified bundle. Also run local report tests, packaging and regression gates.

## Evidence boundaries

This review covers the proposed CLI handoff and reuse of the existing report
writer. It does not accept the broader v1.3 release, external cJSON/libuv
adoption, Docker scale, kind lifecycle, current-revision full release profile,
fresh soak, or independent stable audit. The report is diagnostic evidence,
not an automatic root-cause verdict.
