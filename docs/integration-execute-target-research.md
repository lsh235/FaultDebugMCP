# Integrated target execution: research and decision

Date: 2026-10-17 (Asia/Seoul). Target: v1.3.0-alpha.10.

## Gap

Alpha9 makes the existing-project configure/build/index/bundle path one explicit
command, but users still need to reconstruct and run the plan's launch stage to
obtain their first project capture. The project already has a verified launch
stage and `faultdebug run` writes a `.fault` file after a normal successful exit.
The remaining friction is wiring the built target's arguments into that stage
and checking that the resulting artifact is actually useful.

## Options considered

1. Keep launch manual. Rejected as the only path: it preserves the separation
   but leaves a command-copying step after the first build.
2. Launch automatically after every `--execute-build`. Rejected because it
   would change alpha9's explicit non-launch contract and cause application
   side effects without a separate choice.
3. Add `--execute-target`, accepted only with `--execute-build`, and repeatable
   `--target-arg`. Accepted: the CLI runs the existing generated `run` stage
   only after all four build/evidence stages and bundle verification pass. It
   reports PASS only for one checksum-validated `.fault` artifact with a
   complete, stable, non-empty, loss-free trace and a zero target exit.

Arguments remain individual sequence elements and are never assembled into a
shell command. Python recommends sequence arguments for subprocess calls; this
preserves spaces and shell metacharacters as literal application input. See the
official [Python 3.12 subprocess documentation](https://docs.python.org/3.12/library/subprocess.html).

## Decision and limits

Decision: **YES**, implement the separate explicit target-execution opt-in.
`integrate` remains plan-only by default, and `--execute-build` alone continues
to leave target launch `NOT RUN`. `--execute-target` requires
`--execute-build`; repeated `--target-arg` values are passed in order. A build
failure or unverified bundle prevents launch. A target failure may leave a
useful crash artifact but does not make the combined run PASS.

This runs the selected application as the current user. It is not a sandbox and
may trigger external effects. The command is intended for bounded, explicitly
selected smoke workloads; long-lived services should retain a separately
managed lifecycle. It proves only the one capture summarized by the gate, not
application correctness, full instrumentation coverage, or stable readiness.
