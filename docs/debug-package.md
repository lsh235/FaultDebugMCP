# Package separate ELF debug data

`faultdebug debug-package` prepares one fully linked ELF for a split runtime/debug
distribution. It leaves the input untouched and writes a new directory containing:

```text
package/
  manifest.json
  runtime/my-service
  debug/.build-id/ab/cdef0123456789....debug
```

The Build-ID path is directly usable with `--debug-directory` on `inspect` and
`fault-report`. For MCP, place the `debug/` directory beneath the configured
artifact root and pass its root-relative name as `debug_directory`.

```sh
faultdebug debug-package build/my-service --output dist/my-service-debug
faultdebug debug-verify dist/my-service-debug
faultdebug inspect capture.fault --address 0x401126 \
  --debug-directory dist/my-service-debug/debug
```

The command uses `FAULTDEBUG_OBJCOPY`, `objcopy`, or `llvm-objcopy` in that order;
`--objcopy` selects an explicit executable. It extracts debug sections, strips
all symbols from the copied runtime, then verifies that both outputs retain the
input ELF's GNU Build ID. It also records SHA-256 values in `manifest.json`.
An existing output path is rejected, and intermediate files are discarded if
either objcopy step or any identity check fails.

The input must be a fully linked `ET_EXEC` or `ET_DYN` ELF with a readable GNU
Build ID and DWARF debug sections. This command packages one ELF only; it does
not package shared-library dependencies, source files, split-DWARF companions,
or runtime configuration. A Build ID establishes the binary-side identity
contract, while source citations still require a verified source bundle.

`debug-verify` is a read-only check for a generated package. It verifies the
runtime/debug file hashes recorded in `manifest.json`, requires safe package-
relative paths without symlink escapes, checks the ELF debug sections, and
confirms that both Build IDs equal the manifest value. The source SHA-256 is
recorded but cannot be recomputed because the source ELF is not included.
GNU Build IDs identify the linked file but are not content checksums; the
manifest is unsigned, so these checks establish internal consistency rather
than authenticity or publisher identity.

The flow follows the official [GNU objcopy split-debug procedure](https://sourceware.org/binutils/docs/binutils/objcopy.html)
and produces the [GDB GNU Build-ID directory layout](https://www.sourceware.org/gdb/current/onlinedocs/gdb.html/Separate-Debug-Files.html)
used by FaultDebug's offline resolver. File hashes use Python's documented
[SHA-256 interface](https://docs.python.org/3/library/hashlib.html).
