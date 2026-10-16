# Integrated report language: feature review

Date: 2026-10-17 (Asia/Seoul). Review target: v1.3.0-alpha.12 candidate.

## Review decision

**YES — expose the existing English/Korean report choice in the integrated
workflow.**

This is a small additive usability feature: it removes a second command for
Korean users while preserving alpha11's default output and evidence path. The
report format and translation implementation already exist, so this change
should be limited to CLI validation, argument forwarding, and acceptance
coverage.

## Conditions for acceptance

1. Keep English as the default for compatibility.
2. Accept only the two locales already supported by `fault-report`.
3. Reject the language option unless report generation is explicitly enabled.
4. Test localized JSON, Markdown and HTML from both the direct helper and the
   hosted installed adoption flow; report/target status boundaries stay intact.
