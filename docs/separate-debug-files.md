# Resolve stripped ELF captures with separate debug files

FaultDebug can use a separate ELF debug file when the captured module is stripped
and its symbol table is not present in the executable. Supply one or more local
debug roots. Each root uses the GNU build-ID layout:

```text
symbols/.build-id/ab/cdef0123456789....debug
```

Here `ab` is the first two hexadecimal characters of the module Build ID and the
remaining characters form the filename, followed by `.debug`. FaultDebug checks
that the debug file itself contains the exact Build ID recorded in the capture
before reading its symbols. A misplaced file, absent Build ID, malformed ELF, or
different build is not accepted as a match.

## CLI

Pass the directory that contains `.build-id/` to `inspect` or `fault-report`:

```sh
faultdebug inspect capture.fault --address 0x401126 \
  --debug-directory /srv/faultdebug-symbols

faultdebug fault-report capture.fault --bundle bundles/build-42 \
  --debug-directory /srv/faultdebug-symbols --output reports/incident-42
```

Repeat `--debug-directory` to search multiple explicit roots. Output includes
`debug_file` and `debug_file_build_id` when a matching sidecar contributes to
resolution. Symbol-table reads are cached for the duration of one address batch.

## MCP

The `resolve_addresses` and `get_fault_flow` tools accept the optional
`debug_directory` argument. It must name an existing directory beneath the
server's configured `--root`; place the `.build-id/` hierarchy there. Absolute
paths, parent traversal, and symlink escapes are rejected. For example:

```json
{
  "name": "fault-1234.fault",
  "addresses": [4198694],
  "debug_directory": "symbols"
}
```

The rest of the workflow is unchanged: supply a verified source bundle when
asking for captured source text. `llvm-symbolizer` must be installed/configured
to obtain source locations; the separate ELF may still supply function symbols
without it.

## Scope

- Lookup is local and read-only. No target process runs, files are not copied or
  rewritten, and debuginfod/network lookup is disabled.
- This implementation reads only the `.build-id/xx/rest.debug` layout. It does
  not follow `.gnu_debuglink`, search arbitrary filenames, unpack debug packages,
  or fetch symbols from a server.
- Runtime binary identity is still checked first. The separate file can add
  symbols and DWARF data, but does not establish source provenance by itself;
  source snippets still come only from a verified bundle.
- A matching Build ID verifies binary identity according to the ELF build-ID
  convention. It does not prove that every source file is present or that every
  address has a unique source mapping.

The format and lookup behavior follow the official
[GDB separate-debug-file rules](https://www.sourceware.org/gdb/current/onlinedocs/gdb.html/Separate-Debug-Files.html),
[GNU objcopy split-debug workflow](https://sourceware.org/binutils/docs/binutils/objcopy.html),
and [LLVM symbolizer debug-file-directory option](https://llvm.org/docs/CommandGuide/llvm-symbolizer.html).
