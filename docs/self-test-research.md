# Installed capture self-test: research and decision

Date: 2026-10-17 (Asia/Seoul). Target: v1.3.0-alpha.8.

## Gap

The existing `faultdebug doctor` checks toolchain and runtime availability, but
does not compile a program or prove that one persisted trace can be read. The
runtime smoke in CI exercised an in-repository fixture and the source checkout.
That left a gap between installing the Python package and the first verified
capture through its installed wrapper and CLI.

## Options considered

1. Expand `doctor` to compile and run a program. Rejected because it would turn
   a fast, read-only environment inspection into a build and runtime operation.
2. Document a manual compiler command. Rejected because users would still need
   to assemble the wrapper, runtime path, collector, and artifact checks.
3. Add a separate bounded `faultdebug self-test`. Accepted: it reports setup
   prerequisites first, then uses a fixed generated fixture and temporary
   artifact directory to verify that the installed capture path produced a
   stable, complete trace with events and no reported drops.

## Feasibility and acceptance

A local installed-wheel/native-prefix pilot compiled and launched an output-free
C fixture through the installed wrapper and read back a complete `.fault`
artifact with four events and zero reported thread or RPC drops. The pilot used
the available local compiler only as a feasibility check; it is not the
supported Clang 18 acceptance run. The alpha's hosted Clang 18 job must run the
new command from outside the checkout against the built wheel and upload its
JSON report. A failed prerequisite must stop before compilation and return
`NOT RUN`; a capture contract violation returns `FAIL`.

The project support profile remains Clang 18 on Ubuntu 24.04 x86_64. See the
[GCC function instrumentation documentation](https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html)
for the function-entry/exit instrumentation semantics used by the feasibility
pilot. The product acceptance is the hosted Clang 18 run, not that pilot.

## Decision and limits

Decision: **YES**, implement as an opt-in self-test command and a required
hosted CI check. It executes only generated fixed C source, never a user's
project or binary. It proves one function-event capture and persisted artifact
readability in a bounded run; it does not test source/symbol resolution,
project-wide instrumentation, performance, arbitrary platforms, MCP, or
stable-release acceptance. It removes the temporary artifact after inspection.
