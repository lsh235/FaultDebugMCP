# Integrated report event limit: research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.13`.
Baseline: `v1.3.0-alpha.12` at `4fd13eff8d19cf72c1e9fb9d5a38dff773faead9`.

## User friction

The standalone `faultdebug fault-report` command exposes `--max-events` with a
bounded range of 1–500 per thread. The integrated `faultdebug integrate
--fault-report` path always uses the report builder's default of 80, so a user
who needs a smaller incident view or more retained context must run a second
command against the same artifact and bundle.

The report model already records `omitted_from_view`; reducing the display
limit does not alter the capture or label omitted records as capture loss. The
existing hard ceiling remains 500 per thread, with up to 64 native thread
records accepted by the report model.

## Options

1. Keep the integrated default fixed at 80 and require a second command.
   Rejected because the integrated path now exposes the existing language
   choice but still omits the report's principal size/context control.
2. Add an unbounded value or silently raise the default. Rejected because it
   can produce unexpectedly large HTML and would change alpha12 output.
3. Add `--fault-report-max-events N`, accepting only 1–500, requiring
   `--fault-report`, and defaulting to the existing 80. Accepted for review.
   Forward the value to the existing writer; do not change capture, source
   verification, report status, or output protection.

## Proposed acceptance

- No option keeps alpha12's 80-events-per-thread output.
- Explicit values 1 and 500 reach the report writer unchanged; out-of-range
  and non-integer inputs fail before preparing or executing a build.
- The option without `--fault-report` is rejected before project access.
- A report generated at a smaller limit contains the newest retained events
  and records the omitted display count without changing capture status.
- Target, report, and overall status semantics remain unchanged, including a
  report produced from a nonzero target's validated artifact.
