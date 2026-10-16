# MCP display-title feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.19` candidate.

## Decision

**YES — publish concise, task-specific top-level titles for all 27 MCP tools.**
The current server has short human labels only inside annotations and leaves
the protocol's top-level display title empty. The official SDK exposes the
top-level field, and TDQS receives it as part of the exact tool definition.
Meaningful titles also improve readability in MCP clients that render display
metadata. Alpha18 already pins a compatible SDK, so no package upgrade is
needed.

Keep titles specific to the evidence resource and boundary. Set the annotation
title to the same text to avoid conflicting client labels, and preserve its four
boolean safety hints. This only improves the available definition signal; the
LLM-scored dimensions do not grant a deterministic title bonus and Glama score
change remains unverified.

## Acceptance

1. Real stdio lists 27 unique full-profile titles and the same title values for
   the 15-tool focused subset; each title differs from and is longer than the
   corresponding tool name.
2. Top-level and annotation titles match; existing descriptions, input/output
   schemas, tool names, profile behavior, and safety-hint booleans are retained.
3. Existing invalid-call checks and evidence-file immutability pass.
4. Relevant Python regressions, package build/install checks, and all hosted CI
   jobs pass on the final tagged commit.
5. The release record states Glama pin/deployment/rescan/score as
   NOT VERIFIED unless independently observed.

Stable release acceptance remains **NO-GO**.
