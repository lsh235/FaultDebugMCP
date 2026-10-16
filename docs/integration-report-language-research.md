# Integrated report language: research

Date: 2026-10-17 (Asia/Seoul). Candidate: v1.3.0-alpha.12.
Baseline: v1.3.0-alpha.11 at `ccc10b17740ae2cd076151b0bf8e0e5823aec39b`.

## User friction

The standalone `faultdebug fault-report` command already accepts `--language
en|ko`, and `write_fault_report` sends that choice through the Markdown, JSON
and HTML report builders. The integrated `faultdebug integrate --fault-report`
handoff currently calls the same writer with its English default. Korean users
therefore need to rerun a second manual report command to receive a localized
report.

## Options

1. Keep integrated reports English-only. Rejected because language support
already exists and the extra command restores the path-copying friction that
alpha11 removed.
2. Change the integrated default to Korean. Rejected because it changes the
current alpha11 output without an explicit user choice.
3. Add `--fault-report-language en|ko`, valid only with `--fault-report`, and
keep English as the default. Accepted for review. The implementation will
reuse the existing report writer and translations; it will not add partial or
third-language output.

## Proposed acceptance

- No flag keeps alpha11's English output.
- Explicit `ko` localizes JSON, Markdown and HTML in the same generated folder.
- The language option without `--fault-report` is rejected before build or
  target execution.
- Report, target and overall statuses retain alpha11 behavior for normal and
  failed targets; capture identity, bundle verification and output protection
  are unchanged.
