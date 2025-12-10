# `install-wasi-sdk-action`

[![Cross-platform](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/cross-platform.yml/badge.svg?branch=main)](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/cross-platform.yml)
[![CMake-compatible](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/cmake.yml/badge.svg?branch=main)](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/cmake.yml)
[![Environment-safe](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/env-safe.yml/badge.svg?branch=main)](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/env-safe.yml)
[![Unit tests](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/unit-tests.yml/badge.svg?branch=main)](https://github.com/bytecodealliance/install-wasi-sdk-action/actions/workflows/unit-tests.yml)

This GitHub Action will install the [WASI SDK] toolchain for compiling to WebAssembly on a GitHub
runner:
- Downloads and installs the specified version of WASI SDK (see [releases])
- Optionally adds WASI SDK to the GitHub runner `PATH`
- Sets up [environment variables] and [output variables]

[WASI SDK]: https://github.com/WebAssembly/wasi-sdk
[releases]: https://github.com/WebAssembly/wasi-sdk/releases
[environment variables]: #environment-variables
[output variables]: #output-variables

### Usage

```yaml
- uses: bytecodealliance/install-wasi-sdk-action@v1
# Now, use `clang` or `$CC` to compile C/C++ to WebAssembly:
- run: $CC hello.c -o hello.wasm
```

For more advanced usage, see the following examples:
- [Use with CMake](.github/workflows/cmake.yml)
- [Use without overriding environment](.github/workflows/variables.yml)

### Inputs

| Input          | Description                                | Required | Default                       |
| -------------- | -------------------------------------------| -------- | ----------------------------- |
| `version`      | WASI SDK version to install (e.g., `25`)   | No       | `latest`                      |
| `install-path` | Directory to install WASI SDK to           | No       | `$RUNNER_TOOL_CACHE/wasi-sdk` |
| `add-to-path`  | Add WASI SDK `bin` directory to the `PATH` | No       | `true`                        |

Note that passing `latest` as the `version` will attempt to retrieve the latest [release
tag][releases]. See GitHub's [variables reference] for a description of `RUNNER_TOOL_CACHE`; other
`setup-*` actions store their artifacts here.

[variables reference]: https://docs.github.com/en/actions/reference/workflows-and-actions/variables

### Outputs

| Output             | Description                              |
| ------------------ | ---------------------------------------- |
| `wasi-sdk-path`    | Path to the installed WASI SDK toolchain |
| `wasi-sdk-version` | Version of WASI SDK that was installed   |
| `clang-path`       | Path to the `clang` executable           |
| `sysroot-path`     | Path to the WASI `sysroot`               |

### Environment Variables

When `add-to-path` is `true`, the action adds the WASI SDK `bin` directory to the GitHub runner
`PATH`. It also sets the following environment variables:

- `WASI_SDK_PATH`: Path to the WASI SDK installation
- `CC`: Clang compiler with WASI sysroot configured
- `CXX`: Clang++ compiler with WASI sysroot configured

### Platform Support

This action should be usable on all GitHub runners; open an [issue] if this is not the case.

[issue]: https://github.com/bytecodealliance/install-wasi-sdk-action/issues

| OS      | Architecture | Support |
| ------- | ------------ | ------- |
| Linux   | x86_64       | ✅      |
| Linux   | arm64        | ✅      |
| macOS   | Any          | ✅      |
| Windows | Any          | ✅      |

### License

`install-wasi-sdk-action` is released under the [Apache License Version 2.0][license]. By contributing to
the project, you agree to the license and copyright terms therein and release your contribution
under these terms.

[license]: LICENSE
