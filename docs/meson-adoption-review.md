# Meson adoption feature review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.13`.

## Decision

**NO — defer Meson adoption.** The current Meson wrapper fixture demonstrates
compile-time instrumentation, while `integrate` promises a stronger path:
selected-target runtime linkage, a source-snapshot note embedded before the
link, exact binary identity, immutable source capture, verified bundle, and a
bounded run. The inspected Meson compiler-selection and introspection APIs do
not supply the CMake target mutation lifecycle that currently enforces those
properties. Implementing only the easier compiler-wrapper portion would make
the feature name overstate its evidence.

## Re-entry condition

Research a Meson adapter design that can inject and verify the source note and
runtime for one explicitly selected executable, preserves the original source
and existing build, rejects ambiguous/generated target inputs, and passes the
same normal and fatal adoption acceptance used for CMake. Keep cross builds and
other unsupported layouts explicit until separately tested.

This is a deferred candidate, not an alpha13 implementation or a release
acceptance claim. See the [research record](meson-adoption-research.md).
