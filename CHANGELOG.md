# Changelog

## [0.7.9](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.8...neuralspotx-v0.7.9) (2026-07-19)


### Features

* add named-target flashing and explicit reset API ([1a6ffca](https://github.com/AmbiqAI/neuralspotx/commit/1a6ffcaa556e021f7222ed31e9a95c690149896b))


### Bug Fixes

* restore packaged module scaffolding and align docs ([886ccd6](https://github.com/AmbiqAI/neuralspotx/commit/886ccd64550530f2c176ea7723d12f305af34b54))

## [0.7.8](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.7...neuralspotx-v0.7.8) (2026-07-12)


### Bug Fixes

* **registry:** locate Helia-RT source metadata ([4c1ffb7](https://github.com/AmbiqAI/neuralspotx/commit/4c1ffb7f19b18bbd5c47f0422d2d70426a6c2529))

## [0.7.7](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.6...neuralspotx-v0.7.7) (2026-07-12)


### Features

* **registry:** add stock TFLM NSX modules ([9b7c7b8](https://github.com/AmbiqAI/neuralspotx/commit/9b7c7b8f9ffe0b040cb9cd0d990c105f36ad2410))

## [0.7.6](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.5...neuralspotx-v0.7.6) (2026-07-10)


### Bug Fixes

* **board:** propagate Apollo330 ITCM startup definition ([b676d33](https://github.com/AmbiqAI/neuralspotx/commit/b676d339ad0359fcdc9eb310a7f05b6486274772))

## [0.7.5](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.4...neuralspotx-v0.7.5) (2026-07-08)


### Features

* **app:** add frozen parameter to configure_app/build_app/flash_app ([#178](https://github.com/AmbiqAI/neuralspotx/issues/178)) ([b973776](https://github.com/AmbiqAI/neuralspotx/commit/b973776e2e22dc73868268bc33d3eef80f5dcaf8))


### Documentation

* refresh neuralSPOT-&gt;NSX migration status tables ([#176](https://github.com/AmbiqAI/neuralspotx/issues/176)) ([5636705](https://github.com/AmbiqAI/neuralspotx/commit/56367053617c72c417e2e4205abea6f20fe0d54e))

## [0.7.4](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.3...neuralspotx-v0.7.4) (2026-07-06)


### Features

* **registry:** promote nsx-sensors to first-class, bump nsx-tileio pin ([#173](https://github.com/AmbiqAI/neuralspotx/issues/173)) ([7723bb4](https://github.com/AmbiqAI/neuralspotx/commit/7723bb42dbc451c26327076408cd9619aa940df0))


### Bug Fixes

* **view:** keep SWO viewer alive when stdin is non-interactive ([#175](https://github.com/AmbiqAI/neuralspotx/issues/175)) ([6dafd68](https://github.com/AmbiqAI/neuralspotx/commit/6dafd6880331eee8fc6caa99de1ccd8321f18495))

## [0.7.3](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.2...neuralspotx-v0.7.3) (2026-07-05)


### Features

* **examples:** add host-side BLE smoke tool for ble_webble ([#170](https://github.com/AmbiqAI/neuralspotx/issues/170)) ([00d733a](https://github.com/AmbiqAI/neuralspotx/commit/00d733ab427c5d2befb01803135f2988a858db87))

## [0.7.2](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.1...neuralspotx-v0.7.2) (2026-07-05)


### Bug Fixes

* **registry:** vendor nsx-psram in apollo3/4/5 family sdk_modules ([#168](https://github.com/AmbiqAI/neuralspotx/issues/168)) ([11070f8](https://github.com/AmbiqAI/neuralspotx/commit/11070f875f74086e5e0a21284cbc825dc3c232c1))

## [0.7.1](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.7.0...neuralspotx-v0.7.1) (2026-07-04)


### Features

* **api:** add create_board() public API with BoardCreateRequest DTO ([fb8d921](https://github.com/AmbiqAI/neuralspotx/commit/fb8d9219a79918889fb252dd8b561893d3b049d1))
* **api:** architecture review follow-ups — create_board API, typed errors, board-registry hardening ([#160](https://github.com/AmbiqAI/neuralspotx/issues/160)) ([fb8d921](https://github.com/AmbiqAI/neuralspotx/commit/fb8d9219a79918889fb252dd8b561893d3b049d1))
* **boards:** add Apollo4P EVB Display Shield Rev2 ([d3c6ee9](https://github.com/AmbiqAI/neuralspotx/commit/d3c6ee9e30d2cb09a4c8b1ba0b195a30840b9cbc))


### Bug Fixes

* **boards:** don't set NSX_AMBIQ_HAL_MCU_DIR for apollo2/apollo3 parts ([#159](https://github.com/AmbiqAI/neuralspotx/issues/159)) ([dfa7b9b](https://github.com/AmbiqAI/neuralspotx/commit/dfa7b9b7b087d4f74446c80f55179cc2e1a40161))
* **boards:** enable armclang/ATfE for AP3p and AP4p ([#161](https://github.com/AmbiqAI/neuralspotx/issues/161)) ([4f1ec79](https://github.com/AmbiqAI/neuralspotx/commit/4f1ec79046d4ff68c191dcacdcf44ed18681563f))
* **lock:** make git resolve/sync resilient to transient git failures and hangs ([#157](https://github.com/AmbiqAI/neuralspotx/issues/157)) ([bb6d884](https://github.com/AmbiqAI/neuralspotx/commit/bb6d8845feef6c96cf5e8ecd99d73db30d8cfdd6))
* **registry:** bump nsx-pmu-armv8m to armclang-compat commit ([#162](https://github.com/AmbiqAI/neuralspotx/issues/162)) ([0653cff](https://github.com/AmbiqAI/neuralspotx/commit/0653cff71065a8e15296d85c267706e5560c26b9))

## [0.7.0](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.9...neuralspotx-v0.7.0) (2026-06-24)


### ⚠ BREAKING CHANGES

* `module add/remove` edit only the direct-dep list; the lock is the sole source of the resolved closure.

### Features

* **boards:** consume nsx::bsp seam and restore button capability facts ([#154](https://github.com/AmbiqAI/neuralspotx/issues/154)a.2) ([#156](https://github.com/AmbiqAI/neuralspotx/issues/156)) ([7d388d2](https://github.com/AmbiqAI/neuralspotx/commit/7d388d22aa88b0398c63bc52983f515d56ce795a))
* harmonize dependency model (one modules list: source + targets) ([#151](https://github.com/AmbiqAI/neuralspotx/issues/151)) ([3d8e5bc](https://github.com/AmbiqAI/neuralspotx/commit/3d8e5bcf7e4ec6c92b4e6d7965fb7d11067e4455))
* multi-target follow-ups ([#135](https://github.com/AmbiqAI/neuralspotx/issues/135) steps 3-5) ([#150](https://github.com/AmbiqAI/neuralspotx/issues/150)) ([dc93945](https://github.com/AmbiqAI/neuralspotx/commit/dc93945f095de6a3adb57ffb76b2c150d20fe6be))
* **resolve:** lean manifests + multi-target support ([#135](https://github.com/AmbiqAI/neuralspotx/issues/135) steps 1-2) ([#147](https://github.com/AmbiqAI/neuralspotx/issues/147)) ([b2d841d](https://github.com/AmbiqAI/neuralspotx/commit/b2d841de6ce199cd745d0e50ee481bef15d1fd45))

## [0.6.9](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.8...neuralspotx-v0.6.9) (2026-06-20)


### Features

* **cli:** DX improvements — stale-lock awareness, view capture, app discovery ([#144](https://github.com/AmbiqAI/neuralspotx/issues/144)) ([b10a4e9](https://github.com/AmbiqAI/neuralspotx/commit/b10a4e9f571581d06f9265710d0d484b826d9800))

## [0.6.8](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.7...neuralspotx-v0.6.8) (2026-06-19)


### Bug Fixes

* **apollo4:** align blue BSP dirs and SEGGER targets ([#139](https://github.com/AmbiqAI/neuralspotx/issues/139)) ([d164420](https://github.com/AmbiqAI/neuralspotx/commit/d1644203674a56f01ab58c4ce7853b3e97f6136a))
* **apollo510b:** use shipped system_apollo510 source path ([#140](https://github.com/AmbiqAI/neuralspotx/issues/140)) ([5fb50fa](https://github.com/AmbiqAI/neuralspotx/commit/5fb50fa2bc70a049f27797de2a29ab379255424f))


### Documentation

* refresh NSX site and install guides ([#136](https://github.com/AmbiqAI/neuralspotx/issues/136)) ([4403057](https://github.com/AmbiqAI/neuralspotx/commit/4403057eb4a06af26549538e928b735aaeabba8c))

## [0.6.7](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.6...neuralspotx-v0.6.7) (2026-06-13)


### Bug Fixes

* **nsx-tooling:** declare armclang and atfe toolchain compatibility ([#131](https://github.com/AmbiqAI/neuralspotx/issues/131)) ([dece5de](https://github.com/AmbiqAI/neuralspotx/commit/dece5def1483b379cc865cffb8409cc3051a417c))

## [0.6.6](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.5...neuralspotx-v0.6.6) (2026-06-12)


### Features

* add CM4F FreeRTOS example apps ([#128](https://github.com/AmbiqAI/neuralspotx/issues/128)) ([e9e6c40](https://github.com/AmbiqAI/neuralspotx/commit/e9e6c40c3a651d6abc1667ff37cfe89997fc6b84))
* **examples:** add freertos_blinky Apollo510 reference app ([#122](https://github.com/AmbiqAI/neuralspotx/issues/122)) ([325e68e](https://github.com/AmbiqAI/neuralspotx/commit/325e68e831c491af09ce9c33cfd77c4dc4a757b5))
* support named linker profiles in M55 board modules ([#129](https://github.com/AmbiqAI/neuralspotx/issues/129)) ([8e2790d](https://github.com/AmbiqAI/neuralspotx/commit/8e2790d351d1541d2bb9e1ea932ad1376b0c2ca3))


### Bug Fixes

* preserve skip-on-missing-registry semantics for gitignore entries ([19dc454](https://github.com/AmbiqAI/neuralspotx/commit/19dc4549fe440b318920253b10197a33d40e8db9))
* **registry:** keep nsx-pmu-armv8m standalone on apollo5 ([#124](https://github.com/AmbiqAI/neuralspotx/issues/124)) ([6c26f1f](https://github.com/AmbiqAI/neuralspotx/commit/6c26f1fa48c26af4e619ebdb92f6bcf9ac0e4b80))
* resolve local module CMake dir to project clone dir ([57b1eb8](https://github.com/AmbiqAI/neuralspotx/commit/57b1eb814509e2f01b6603cd9f4c9e6662b31a14))
* resolve local module CMake dir to project clone dir ([f80bbe0](https://github.com/AmbiqAI/neuralspotx/commit/f80bbe0c8b6a36d0872420490a8bfa9941b667f8))
* resolve local-module gitignore + project dir to project clone path ([1872d2e](https://github.com/AmbiqAI/neuralspotx/commit/1872d2ee045a9abd65a6720e02ee88b687e1d807))

## [0.6.5](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.4...neuralspotx-v0.6.5) (2026-06-11)


### Bug Fixes

* deterministic uv.lock version sync in release ([7b4764b](https://github.com/AmbiqAI/neuralspotx/commit/7b4764b8736a3199eb03380c09484b52c8c98bc0))
* make release downstream jobs robust to skipped deps ([5818bf8](https://github.com/AmbiqAI/neuralspotx/commit/5818bf8739d4f4a2a36ebc050f8ef2a61c0a4c48))

## [0.6.4](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.3...neuralspotx-v0.6.4) (2026-06-11)


### Features

* auto refresh uv.lock after release ([47589b9](https://github.com/AmbiqAI/neuralspotx/commit/47589b951b0db5ea58b12389e6fb72508fed04e7))


### Bug Fixes

* constrain release uv.lock refresh ([0a5daae](https://github.com/AmbiqAI/neuralspotx/commit/0a5daaeaa3ac750483a4311fafc44d40cedc9500))
* release workflow tag validation ([#116](https://github.com/AmbiqAI/neuralspotx/issues/116)) ([77d0001](https://github.com/AmbiqAI/neuralspotx/commit/77d0001d0e36fe4c4df0d8c8d8b86b4a7632ac2e))

## [0.6.3](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.2...neuralspotx-v0.6.3) (2026-06-11)


### Features

* Release and publish to PyPI ([#114](https://github.com/AmbiqAI/neuralspotx/issues/114)) ([e8a09ba](https://github.com/AmbiqAI/neuralspotx/commit/e8a09ba3f74380e170012983e7b6318bbdc10a5a))

## [0.6.2](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.1...neuralspotx-v0.6.2) (2026-06-10)


### Features

* add unified sdk provider plumbing ([0ed922b](https://github.com/AmbiqAI/neuralspotx/commit/0ed922bb4209598878da4fa26f3fd0ddddd13c2c))
* **boards:** land board descriptors and registry refactor ([#100](https://github.com/AmbiqAI/neuralspotx/issues/100)) ([3fc226c](https://github.com/AmbiqAI/neuralspotx/commit/3fc226c4355b7abff34069761219c827682e42af))
* **cli:** add nsx probes command ([#105](https://github.com/AmbiqAI/neuralspotx/issues/105)) ([fd1a8b0](https://github.com/AmbiqAI/neuralspotx/commit/fd1a8b04d3e50929c414b74dc701d0d21abdf3fe))
* **cli:** support selecting a J-Link probe by serial ([#102](https://github.com/AmbiqAI/neuralspotx/issues/102)) ([ff5e513](https://github.com/AmbiqAI/neuralspotx/commit/ff5e513edcd44ab824dc21b8a8e3cde894f12105))
* **examples:** migrate maintained apps to nsx modules ([a3ef9e7](https://github.com/AmbiqAI/neuralspotx/commit/a3ef9e7716f35dff87e111e5fb27cd9073b82479))
* **examples:** migrate maintained apps to nsx modules ([28a096a](https://github.com/AmbiqAI/neuralspotx/commit/28a096a37e6364f8b3dd35d691ccd93337d8966c))
* migrate kws_infer to nsx PMU APIs ([d681436](https://github.com/AmbiqAI/neuralspotx/commit/d681436b3fdb4c782ab85bf86cab191c3643c8cd))
* **platform:** add Atomiq110 FPGA board and R6 SDK tier ([#104](https://github.com/AmbiqAI/neuralspotx/issues/104)) ([d074fb3](https://github.com/AmbiqAI/neuralspotx/commit/d074fb300704e327178fea0bd03d2b774bb72d2b))
* publish registry helpers and profile-owned starter modules ([8aea048](https://github.com/AmbiqAI/neuralspotx/commit/8aea048fbc821411f6216f5b3fb552fe81401948))
* **registry:** source R3-R5 SDKs from consolidated nsx-ambiq-sdk monorepos ([#103](https://github.com/AmbiqAI/neuralspotx/issues/103)) ([ca8d95b](https://github.com/AmbiqAI/neuralspotx/commit/ca8d95ba81908872ab6d4d4c9c2644a2e5896c9d))
* Using temporary file to replace depreciated commandfile ([143a8a9](https://github.com/AmbiqAI/neuralspotx/commit/143a8a962e366e26b56d62502a6efadca2e7c8f8))


### Bug Fixes

* align KWS example with merged NSX module updates ([9c63ef8](https://github.com/AmbiqAI/neuralspotx/commit/9c63ef8d7a689e63a0b33b4bc93c8e62f54f2749))
* align pmu example config with output ([#109](https://github.com/AmbiqAI/neuralspotx/issues/109)) ([3964ae7](https://github.com/AmbiqAI/neuralspotx/commit/3964ae70974a5da22a85210fcf0a8d5d18663bfb))
* **boards:** use AmbiqSuite CMSIS system_apollo4p.c for startup ([5ba22f0](https://github.com/AmbiqAI/neuralspotx/commit/5ba22f084413fe7446f3d727ccc4fe1ff534bec8))
* include NSX headers directly in KWS C++ ([77b2320](https://github.com/AmbiqAI/neuralspotx/commit/77b23207b9cad7283392d6656f765378a292ce91))
* migrate example apps to nsx core apis ([07ede51](https://github.com/AmbiqAI/neuralspotx/commit/07ede510edbdc0e6543cadf3f45f31092a7232b7))
* **pmu_profiling:** bump nsx-pmu-armv8m to readable print format ([43cde4c](https://github.com/AmbiqAI/neuralspotx/commit/43cde4cc79af1107da53c8adaa3a2ef62479874f))
* point unified core modules at nsx-ambiq-sdk ([#113](https://github.com/AmbiqAI/neuralspotx/issues/113)) ([1684426](https://github.com/AmbiqAI/neuralspotx/commit/1684426ab1d7bef5f2cb59135301f009ea9afe9a))
* refresh apollo510 example validation slice ([e55819e](https://github.com/AmbiqAI/neuralspotx/commit/e55819ea6728215b2fd4571a4b520a0ab0a29163))
* refresh example locks for merged modules ([3bb9fe5](https://github.com/AmbiqAI/neuralspotx/commit/3bb9fe5d4031527af2ee30059d9ac9976a22c344))
* refresh floating refs during lock ([a335f6b](https://github.com/AmbiqAI/neuralspotx/commit/a335f6ba0fd851ec15e919ec05f71bfd68f0b53f))
* relock kws_infer against merged R5 SDK ([4f07c34](https://github.com/AmbiqAI/neuralspotx/commit/4f07c34929d5b2b09648bf96bf1c0c41da2fa999))
* simplify pmu profiling example output ([#108](https://github.com/AmbiqAI/neuralspotx/issues/108)) ([654c4a6](https://github.com/AmbiqAI/neuralspotx/commit/654c4a6ca2a367fcea30fb2e41830c6163b0a95c))
* stabilize local-source sync hashing ([d08a750](https://github.com/AmbiqAI/neuralspotx/commit/d08a7504a8c4a02619a3aeac369ab8bea9c73879))

## [0.6.1](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.6.0...neuralspotx-v0.6.1) (2026-05-14)


### Features

* add -fshort-wchar for armclang and select .lib prebuilt format ([c7a13b8](https://github.com/AmbiqAI/neuralspotx/commit/c7a13b88f75e2edfb959023b55bd07d372f48495))
* ATfE toolchain docs, apollo510dL_evb board, ambiqsuite-r5 v0.2.1, and `nsx clean --reset` ([#89](https://github.com/AmbiqAI/neuralspotx/issues/89)) ([d23fe2e](https://github.com/AmbiqAI/neuralspotx/commit/d23fe2ea2b65db75f453e659dce9b20e18aa997b))

## [0.6.0](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.5.1...neuralspotx-v0.6.0) (2026-05-12)

This is the v1-readiness release. All seven phases of the architectural
review are complete: the public API surface is frozen, on-disk formats
are versioned, the CLI has structured output, supply-chain hardening is
in place, large modules are decomposed, and UX/cross-platform/quality
polish has landed.

### Features — CLI UX polish (G1–G5, D1) ([#68](https://github.com/AmbiqAI/neuralspotx/issues/68))

* **Tiered `nsx --help`** groups commands into Quickstart, Modules,
  Maintenance, and Introspection sections.
* **Top-level aliases:** `nsx add` → `nsx module add`,
  `nsx list-modules` → `nsx module list`.
* **Bare `nsx`** now prints help instead of a traceback.
* **`nsx commands`** lists every subcommand with scope/category metadata.
* **`--app-dir` auto-discovery** extended to all `nsx module` subcommands.
* **`nsx module init --summary`** default placeholder no longer starts with `TODO:`.

### Features — cross-platform robustness (B5/B6/B8) ([#68](https://github.com/AmbiqAI/neuralspotx/issues/68))

* **`surrogateescape` encoding** on all subprocess pipes so non-UTF-8
  compiler output never crashes NSX.
* **Windows `rmtree`** retry-after-`chmod` now calls the original
  failing function instead of unconditional `os.unlink`.
* **`pathlib.PurePosixPath`** used for all generated CMake / Makefile
  paths so forward slashes are emitted on every OS.

### Features — Hypothesis property-based tests (H2) ([#68](https://github.com/AmbiqAI/neuralspotx/issues/68))

* 11 new Hypothesis property tests covering `NsxProject` round-trip,
  `Event` construction, SBOM generation, `NsxLock` I/O, emitter
  `ContextVar` isolation, module-change records, outdated report,
  doctor report, cache schema migration, `DoctorCheck` ordering, and
  `CommandDescriptor` round-trip.

### Features — supply-chain hardening & SBOM ([#66](https://github.com/AmbiqAI/neuralspotx/issues/66))

Three small additions make the v1 supply-chain story complete: every
`git` invocation is restricted to safe transports, `nsx sync --frozen`
catches mid-tree tampering by name, and apps can publish a Software
Bill of Materials in one command.

* **Pinned `git` protocol allow-list.** Every `git` invocation issued
  by `git_clone_at_commit` and `git_clone` is now prefixed with
  `-c protocol.allow=user -c protocol.ext.allow=never -c
  protocol.file.allow=never`. Registry URLs are also validated in
  Python before `git` is invoked: `ext::…`, `file://…`, `file::…`
  and any other non-allow-listed scheme are refused with a typed
  `NSXGitError` whose message names the offending protocol. The
  `nsx doctor` report includes an informational line listing the
  active allow-list flags.
* **`nsx sync --frozen` integrity verification.** The frozen path
  re-hashes every vendored module against its lock-recorded
  `content_hash` and now raises the new `NSXIntegrityError`
  (subclass of `NSXModuleError`) whose `module` attribute names the
  offending entry. Existing `except NSXModuleError` sites continue
  to catch the failure unchanged.
* **`nsx sbom` (and `api.generate_sbom`).** New CLI subcommand
  `nsx sbom [--format spdx|cyclonedx] [--output FILE]` and the
  matching `neuralspotx.generate_sbom(app_dir, *, format="spdx") -> str`
  emit a single-document SBOM derived from `nsx.lock`: per-module
  upstream URL, commit SHA, and content hash. Default format is
  SPDX 2.3 JSON; CycloneDX 1.5 JSON is also supported. License
  metadata is currently emitted as `NOASSERTION` until a follow-up
  phase wires it through.
* **Public errors:** `NSXGitError`, `NSXIntegrityError`.
* **Public callable:** `generate_sbom`.

### Features — structured event emitter & --json output ([#65](https://github.com/AmbiqAI/neuralspotx/issues/65))

The Python API and CLI gain a structured output channel so embedders
(IDE plugins, Helia profiler, CI dashboards) can render NSX progress
without screen-scraping `print()` calls.

* **`neuralspotx.Event` / `neuralspotx.Emitter`.** `Event(kind, message, data)`
  is the new immutable carrier for everything NSX would otherwise have
  printed. `kind` is one of `"info"` / `"warn"` / `"error"` / `"step"` /
  `"line"`. `Emitter` is the public type alias `Callable[[Event], None]`.
  `neuralspotx.default_emitter` routes `line` to stdout and the rest to
  stderr.
* **`emit=` kwarg on every printing API entry point.** `create_app`,
  `doctor`, `configure_app`, `build_app`, `flash_app`, `view_app`,
  `clean_app`, `lock_app`, `sync_app`, and `update_app` now accept an
  optional `emit: Emitter | None = None` keyword. Inside each call the
  supplied emitter is installed via a `ContextVar` so the entire nested
  operations layer routes through it without any further plumbing. All
  27 ad-hoc `print()` sites in `operations/` and `tooling.py` migrated
  to the new `info()`/`warn()`/`line()` helpers.
* **`on_line=` kwarg on `build_app` / `flash_app`.** The build and
  flash entry points additionally accept `on_line: Callable[[str], None]`
  which receives every subprocess line as it is produced. Subprocess
  stdout and stderr are merged so consumers see them in temporal order;
  the parent's stdout is still written to so user-visible output is
  unchanged. Threaded through `subprocess_utils.run` while preserving
  process-tree timeout and Ctrl-C semantics.
* **`--json` output on four CLI commands.** `nsx doctor --json`,
  `nsx cache info --json`, `nsx commands --json`, and
  `nsx module list --json` emit a single JSON document on stdout that
  matches the `to_dict()` shape of the corresponding dataclass. The
  default human-readable output is unchanged.

### Features — formats freeze ([#64](https://github.com/AmbiqAI/neuralspotx/issues/64))

Two on-disk formats are now versioned and validated up front so that
post-v1.0 changes never silently break user data.

* **`nsx.yml` typed loader.** New `neuralspotx.models.NsxProject` is
  the canonical typed view of an app manifest. `NsxProject.from_yaml`
  validates every structural field (root schema_version, project
  mapping, project.name, target/board types, toolchain, modules list
  with per-entry checks, module_registry, tooling, profile fields)
  and raises `NSXConfigError` whose new `.field` attribute names the
  offending YAML key path (e.g. `"modules[2].name"`). Unknown
  top-level keys round-trip via `NsxProject.extra` so adding fields
  in a future minor release is non-breaking. `NsxProject.to_yaml(path)`
  re-emits an equivalent manifest (modulo formatting). All `nsx.yml`
  reads inside `_load_app_cfg` now route through this loader so a bad
  manifest surfaces as a typed, field-tagged error rather than an
  opaque `KeyError` deep in the operations layer.
* **`git-artifact-hashes.json` schema_version.** The user-cache file
  at `$NSX_CACHE_DIR/git-artifact-hashes.json` now writes a v1
  header (`{"schema_version": 1, "entries": {...}}`). The reader
  tolerates absent headers by treating the legacy flat-mapping layout
  as v1 (so existing user caches keep working) and aborts with the
  new `NSXCacheError` — pointing to `nsx cache clean` — if it sees a
  higher version than this nsx supports.
* **New typed exception:** `NSXCacheError` (subclass of `NSXError`)
  exported from `neuralspotx`. `NSXConfigError` gained an optional
  `.field` attribute carrying the offending YAML key path.

### Features — API freeze ([#61](https://github.com/AmbiqAI/neuralspotx/issues/61))

The public Python surface is locked before v1. All typed results are
re-exported from `neuralspotx` so embedders no longer need to import
private modules.

* **Public re-exports:** `NsxLock`, `ResolvedModule`, `LockKind`,
  `OutdatedStatus`, `ProfileStatus`, `CommandCategory`, `CommandScope`,
  `DoctorReport`, `DoctorCheck`, `OutdatedReport`, `ModuleChange`,
  `CacheInfo`.
* **`create_app` returns `Path`** to the created directory.
* **`py.typed` marker** added for PEP 561 typed-package compliance.

### Refactoring — file decomposition ([#67](https://github.com/AmbiqAI/neuralspotx/issues/67))

Five oversize modules split into packages with backwards-compatible
re-exports:

* `cli.py` → `cli/` package (parsers, per-command modules, render helpers).
* `models.py` → `models/` package.
* `nsx_lock.py` → `nsx_lock/` package (resolution, hashing, I/O).
* `subprocess_utils.py` → `subprocess_utils/` package (git, process management).
* `api.py` → `api/` package; `module_registry.py` → `module_registry/` package.

### Refactoring — pre-phase architectural cleanup

Landed between 0.5.1 and Phase 1 as part of the REVIEW/REVIEW2
backlog:

* **Typed errors:** `NSXError` hierarchy replaces `SystemExit` raises
  throughout; `ResolutionError` added for lock resolution failures.
* **Structured logging:** `-v`/`-vv`/`-q` verbosity flags via `ContextVar`.
* **Typed domain objects:** `DoctorReport`, `OutdatedReport`,
  `ModuleChange`, `CacheInfo`, `NsxLock`, `CommandDescriptor`.
* **API completeness:** all CLI module commands routed through `api.*`.
* **Windows process-tree reaping** via `KILL_ON_JOB_CLOSE` Job Object.
* **`.gitattributes`** + non-UTF-8 CI lane + `ruff PLW1514` enforcement.
* **Board/SoC normalization** made case-insensitive at input boundaries.
* **`cmake-vendor-diff` CI job** detects drift between vendored and
  generated cmake/nsx files.

### Bug Fixes

* **Security:** `git ls-remote` in `nsx_lock/_resolution.py` now
  validates URLs and applies the protocol allow-list
  ([#75](https://github.com/AmbiqAI/neuralspotx/issues/75),
  [#79](https://github.com/AmbiqAI/neuralspotx/pull/79)).
* **Windows `rmtree`:** `_on_rm_error` retries the original failing
  function instead of unconditional `os.unlink`
  ([#76](https://github.com/AmbiqAI/neuralspotx/issues/76),
  [#79](https://github.com/AmbiqAI/neuralspotx/pull/79)).
* **`nsx module init` placeholder:** default summary changed from
  `"TODO: describe what …"` to a neutral placeholder
  ([#77](https://github.com/AmbiqAI/neuralspotx/issues/77),
  [#80](https://github.com/AmbiqAI/neuralspotx/pull/80)).
* **`py.typed` + pyproject metadata:** added PEP 561 marker and filled
  in missing classifier/URL fields
  ([#81](https://github.com/AmbiqAI/neuralspotx/pull/81)).
* Excluded auto-generated `modules.cmake` from `nsx-tooling` content
  hash ([#36](https://github.com/AmbiqAI/neuralspotx/pull/36)).
* `file_lock` reentrancy and warn-once made thread-safe
  ([#33](https://github.com/AmbiqAI/neuralspotx/pull/33)).
* `shutil.rmtree(onexc=)` used on Python 3.12+
  ([#32](https://github.com/AmbiqAI/neuralspotx/pull/32)).

### ⚠ BREAKING CHANGES — pre-1.0 compat surface removed

These removals close out [#63](https://github.com/AmbiqAI/neuralspotx/issues/63)
in preparation for v1.0. Anything documented as "kept for backwards
compatibility" or "legacy wrapper" pre-0.6 is gone.

* **nsx_lock:** removed `LegacyLockError`. `read_lock()` now raises the
  standard `NSXLockError` on schema mismatch and no longer accepts
  `allow_legacy=`. `NSXLockError`'s docstring is broadened to cover
  both advisory-lock acquisition failures and on-disk lock-file
  schema/format incompatibilities (which is what callers were
  already catching in practice).
* **file_lock:** removed the `NSX_LOCK_FAIL_OPEN=1` escape hatch.
  `app_lock()` is unconditionally fail-closed when the platform lock
  primitive errors. `AppLockBusyError` and `AppLockUnavailableError`
  now subclass `NSXLockError` so they participate in the standard
  `NSXError` classification path in `cli.main` instead of falling
  through as unclassified `RuntimeError`s. Removed the unused
  `_warn_once` / `_warned` helpers.
* **api:** removed the `as_json` field from `AppOutdatedRequest` and
  the `as_json=` parameter from `outdated_app()`. Callers that need
  machine-readable output should use `OutdatedReport.to_dict()`.
* **subprocess_utils:** removed the `_terminate_tree(proc)` wrapper.
  Internal call sites already use `_ProcessContainer` directly.

### Documentation

* Restructured the neuralSPOT→NSX coverage tables in
  `docs/contributing/module-coverage.md` under a new
  "Historical mapping (neuralSPOT → nsx)" section so their
  retrospective intent is unambiguous.

## [0.5.1](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.5.0...neuralspotx-v0.5.1) (2026-05-08)


### Features

* **api:** per-call timeout_s with process-group kill on expiry ([#23](https://github.com/AmbiqAI/neuralspotx/issues/23)) ([0be0cc6](https://github.com/AmbiqAI/neuralspotx/commit/0be0cc68877a2b239c06a24278ce2b44ebd1d3c0))
* **cache:** content-addressed cache for vendored module artifacts ([#22](https://github.com/AmbiqAI/neuralspotx/issues/22)) ([6093aca](https://github.com/AmbiqAI/neuralspotx/commit/6093aca95a3ab23c27585ecf6c6020ba915349ce))
* **examples:** multi-toolchain prebuilts + power-benchmark tuning ([#24](https://github.com/AmbiqAI/neuralspotx/issues/24)) ([d9dca55](https://github.com/AmbiqAI/neuralspotx/commit/d9dca558a5405e3de6a83a43a9803128cb31b9bc))
* **nsx:** review-driven fixes + Py3.12 rmtree fix + nsx-core v0.2.0 bump ([#29](https://github.com/AmbiqAI/neuralspotx/issues/29)) ([a94c877](https://github.com/AmbiqAI/neuralspotx/commit/a94c877e40f86c53bb661da9543bb02ffe3301d2))


### Bug Fixes

* **nsx-lock:** atomic writes, read-only --check, per-app lock, viewer cleanup ([#26](https://github.com/AmbiqAI/neuralspotx/issues/26)) ([eb1541e](https://github.com/AmbiqAI/neuralspotx/commit/eb1541e2cb20eb85f34daf4755924d3cc50676ee))


### Performance Improvements

* **nsx:** parallel resolve_ref + hash_git_artifact + outdated ([#27](https://github.com/AmbiqAI/neuralspotx/issues/27)) ([74007dd](https://github.com/AmbiqAI/neuralspotx/commit/74007dd7e0834fd1529b56e773a2fd9f26e5ae87))
* **nsx:** persistent TTL cache for resolve_ref (git ls-remote) ([fecf000](https://github.com/AmbiqAI/neuralspotx/commit/fecf0002abe5848dffcd4892293fd7973d94f06a))


### Documentation

* lead with app-centric flow; demote clone-the-repo path ([#19](https://github.com/AmbiqAI/neuralspotx/issues/19)) ([a5d0cd1](https://github.com/AmbiqAI/neuralspotx/commit/a5d0cd1c7afb33d17b1357876f36eb322e1c5511))

## [0.5.0](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.4.0...neuralspotx-v0.5.0) (2026-04-30)


### ⚠ BREAKING CHANGES

* **operations:** `nsx.lock` schema is now version 3. `content_hash` records the upstream artifact (git tree at the locked commit, or the packaged source tree) rather than the materialized `modules/<name>/` tree. Apps with a v1/v2 lock must re-run `nsx lock` once to migrate; the file is regenerated automatically the first time `nsx sync` runs without a current lock.

### Code Refactoring

* **operations:** always lock before sync; drop branch-tip fallback ([#20](https://github.com/AmbiqAI/neuralspotx/issues/20)) ([0122a76](https://github.com/AmbiqAI/neuralspotx/commit/0122a764071c94ff3ae69bd5faf0750de3604a82))

## [0.4.0](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.3.0...neuralspotx-v0.4.0) (2026-04-29)


### ⚠ BREAKING CHANGES

* nsx.lock schema v2 (drop ref, add tag, peeled commit SHAs) ([#15](https://github.com/AmbiqAI/neuralspotx/issues/15))

### Features

* nsx.lock schema v2 (drop ref, add tag, peeled commit SHAs) ([#15](https://github.com/AmbiqAI/neuralspotx/issues/15)) ([b166b06](https://github.com/AmbiqAI/neuralspotx/commit/b166b061cb092e44cff5f4485208c20089e14519))

## [0.3.0](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.2.0...neuralspotx-v0.3.0) (2026-04-29)


### Features

* add apollo4b_blue_evb board support ([35bd70d](https://github.com/AmbiqAI/neuralspotx/commit/35bd70d28b996667f97bd4dc8435b440f505c8a1))
* add ATfE toolchain support alongside GCC and armclang ([#12](https://github.com/AmbiqAI/neuralspotx/issues/12)) ([77bfd3e](https://github.com/AmbiqAI/neuralspotx/commit/77bfd3eb7427a4628ce91713d5635ec3ff99bf6f))
* add custom module scaffolding command ([a433da6](https://github.com/AmbiqAI/neuralspotx/commit/a433da61e7d40508e42307de9ff3f110b2d8a190))
* armclang/ATfE toolchains, lock-mechanism CI, and v0.1.0 nsx-module pins ([#13](https://github.com/AmbiqAI/neuralspotx/issues/13)) ([724c84a](https://github.com/AmbiqAI/neuralspotx/commit/724c84a1919c6d25a0d3a14571ff339c81cc8ac0))
* first-class armclang support + cross-platform CI ([f0fad50](https://github.com/AmbiqAI/neuralspotx/commit/f0fad509cfad74ea819fb425bc2ac704f8b73393))
* **power_benchmark:** add SDK5-mimic mode and register dump ([cffa4d0](https://github.com/AmbiqAI/neuralspotx/commit/cffa4d08a01cf92fe3d88912374ebbfc7ed7f4c8))
* **toolchain:** enable armclang builds across all examples ([#11](https://github.com/AmbiqAI/neuralspotx/issues/11)) ([9431e74](https://github.com/AmbiqAI/neuralspotx/commit/9431e7419e9a77799afbf553209394c12cf82cf8))


### Bug Fixes

* **ci:** correct arm64 macOS URL, Windows PATH encoding, skip kws_infer ([bda80c0](https://github.com/AmbiqAI/neuralspotx/commit/bda80c0a2dbec491625dd5bc595b75cb4d2b68e5))
* **ci:** find arm-none-eabi-gcc.exe dynamically on Windows ([6a52e4e](https://github.com/AmbiqAI/neuralspotx/commit/6a52e4e20bd852b4157b1ef1c3412e3414e7c27e))
* **ci:** handle unquoted version in nsx-module-ci template ([0f29fae](https://github.com/AmbiqAI/neuralspotx/commit/0f29faeea78027477b8526fac4c5a88a4924626c))
* **ci:** switch Windows ARM GCC install from pwsh to bash ([59399fe](https://github.com/AmbiqAI/neuralspotx/commit/59399fe19ff46b8b1f96b40fdacd7a41bf840863))
* **ci:** use mingw-w64-i686 ARM GCC for Windows (official 14.2.rel1 package) ([5330183](https://github.com/AmbiqAI/neuralspotx/commit/53301834630ad7ca5db8594efc2a9211b1cbefcc))
* **coremark:** armclang toolchain uses .elf suffix and clears standard libs ([6726c6a](https://github.com/AmbiqAI/neuralspotx/commit/6726c6a996139bdc8616eb2c554487be9d4953e0))
* **docs:** replace symlinks with snippet includes, use custom logo icon, fix hero sizing ([53200ce](https://github.com/AmbiqAI/neuralspotx/commit/53200cef3c87a63cbeeca0876c778263807dde2a))
* **examples:** update nsx.yml from deleted r5.3 to main, expand coremark README ([a7e2619](https://github.com/AmbiqAI/neuralspotx/commit/a7e2619a1e808aacbdbe9cdfe1de90800d387c11))
* handle read-only Git pack files on Windows in rmtree ([f7c0a22](https://github.com/AmbiqAI/neuralspotx/commit/f7c0a22b9f89f5ac1e8c4683697a022bcaa2d1c7))
* make module catalog tables locally searchable ([5eacef2](https://github.com/AmbiqAI/neuralspotx/commit/5eacef2513d48932e01bf735fff7803c8b65a511))
* use colored docs navbar icon ([84aba23](https://github.com/AmbiqAI/neuralspotx/commit/84aba2350442b7cb5c54d3a7ff49ca02000fa6c7))


### Documentation

* add module catalog with searchable table and custom module walkthrough ([20a2f9d](https://github.com/AmbiqAI/neuralspotx/commit/20a2f9db0c69a1f27887a2e4f1455a875f22a466))
* add searchable paginated module tables ([9877250](https://github.com/AmbiqAI/neuralspotx/commit/9877250c16f5c76c7d3e79afe337a6543b65f344))
* clean landing page revamp — consistent section widths, full-bleed alternating backgrounds ([dc7a86f](https://github.com/AmbiqAI/neuralspotx/commit/dc7a86f338497ff5e7f5022c63ee86b79a93488c))
* consolidate module pages, pin navbar colors, fix stale content ([d8a6844](https://github.com/AmbiqAI/neuralspotx/commit/d8a68444f8fd6e85425d7361bc00b4eb5798129e))
* enrich example READMEs, add mkdocs examples section, fix CI and Pages deploy ([1d88fc1](https://github.com/AmbiqAI/neuralspotx/commit/1d88fc1faff63de0b58c94d27bdcb92ad6ad4706))
* enrich Getting Started — more content, tables, cards, cleaner tone ([0ec32ae](https://github.com/AmbiqAI/neuralspotx/commit/0ec32aedc5985eb145068fd85ac85225193d9ee1))
* examples landing page, neutral translucent header ([1ffd595](https://github.com/AmbiqAI/neuralspotx/commit/1ffd5956a7e11fde25150893729bd468c792b3be))
* fix material icons, redesign workflow + where-to-start as cards ([00f781d](https://github.com/AmbiqAI/neuralspotx/commit/00f781dd6eb019de466cffffa4c855cc47663bb4))
* flat modern landing page redesign — clean cards, centered sections, code snippet ([122b173](https://github.com/AmbiqAI/neuralspotx/commit/122b1739d94ffb116859296f5f0a52bba0faa777))
* modern landing page with logo, wider layout, dark/light theme, feature cards ([baf59fa](https://github.com/AmbiqAI/neuralspotx/commit/baf59fa2ccf2b9d631d70eb70b235d5c618a7a70))
* overhaul landing page — larger logo, teal hex workflow, ecosystem diagram, richer content ([48a7c7d](https://github.com/AmbiqAI/neuralspotx/commit/48a7c7d1c4c446a106baff0ca1a4319da4f7d90f))
* remove specific power/current numbers from coremark example ([d73e95d](https://github.com/AmbiqAI/neuralspotx/commit/d73e95d2403dda81525e2e5aeaf1ce9923f19f4d))
* reorder homepage flow and add compact quick-links section ([cff426a](https://github.com/AmbiqAI/neuralspotx/commit/cff426abd7a3c38dfe6810534641daa0aac39386))
* replace mermaid workflow with custom SVG pipeline graphic ([4ba932c](https://github.com/AmbiqAI/neuralspotx/commit/4ba932c6beaafbd8b0278cbd74f655a89fc32fe6))
* simplify landing page — pure markdown, material grid cards, minimal CSS, fix search input ([05f9a46](https://github.com/AmbiqAI/neuralspotx/commit/05f9a4677a2fbb202e221b848840e85247deefa1))
* use standard material navbar, enable full feature set (annotations, tabs, details, grids, keys, tasks) ([bf3efa0](https://github.com/AmbiqAI/neuralspotx/commit/bf3efa0bcd494a0e5c9d0422754574858e8ec060))
* use white navbar icon ([7ae2a8d](https://github.com/AmbiqAI/neuralspotx/commit/7ae2a8d858b8811162b43b5807d8cbf5d5c52350))
* widen grid max-width to 1840px ([1ea557d](https://github.com/AmbiqAI/neuralspotx/commit/1ea557df1b030d1b9dd7de63a249b9f981132d90))
* widen home landing layout and tighten card typography ([e6065ba](https://github.com/AmbiqAI/neuralspotx/commit/e6065babba11ce6d79f2b6b59c62eceb95e0edb2))

## [0.2.0](https://github.com/AmbiqAI/neuralspotx/compare/neuralspotx-v0.1.0...neuralspotx-v0.2.0) (2026-04-09)


### Features

* add coremark + power_benchmark examples, CI/release template ([d0f4b60](https://github.com/AmbiqAI/neuralspotx/commit/d0f4b60e491e7fba42d82448a79d0d4feb9cd6b6))
* add nsx-nanopb module + usb_rpc example ([#7](https://github.com/AmbiqAI/neuralspotx/issues/7)) ([f4c1e19](https://github.com/AmbiqAI/neuralspotx/commit/f4c1e19d656f1d04fab0ad7799351c749c3f10ed))
* app-first architecture, local modules, examples, linker fix ([#6](https://github.com/AmbiqAI/neuralspotx/issues/6)) ([216f1af](https://github.com/AmbiqAI/neuralspotx/commit/216f1af7a0f2b8fca500c271aa89fb402d7449e5))
* kws_infer example, SEGGER fixes, create-app bugfix, docs ([1ff9dab](https://github.com/AmbiqAI/neuralspotx/commit/1ff9dab4797c1034e8f337d9292f17ecccd56ba3))
* trigger release for issue [#8](https://github.com/AmbiqAI/neuralspotx/issues/8) ([#9](https://github.com/AmbiqAI/neuralspotx/issues/9)) ([cda2280](https://github.com/AmbiqAI/neuralspotx/commit/cda228016ca39c1897f18f9963eaa29a02c79370))


### Bug Fixes

* add enum aliases for nanopb-generated NsxRpcMsgType values ([a79ad83](https://github.com/AmbiqAI/neuralspotx/commit/a79ad83d23f4dc7f17f07ed8fea2b2dd6f3d41e4))
* default missing manifest revisions ([0654a4a](https://github.com/AmbiqAI/neuralspotx/commit/0654a4ac4075a97737e85d4e717458fd9c5963f7))
* examples uv group + rpc_host.py grpcio-tools codegen ([74347b2](https://github.com/AmbiqAI/neuralspotx/commit/74347b2c1a228c451e82b76765d62470b00036f8))
* preserve vendored module metadata paths ([89f9e8e](https://github.com/AmbiqAI/neuralspotx/commit/89f9e8eb85ce89d2fa83aca92a29761e1afafd0d))
* resolve ruff lint errors in joulescope_capture.py ([27ebedd](https://github.com/AmbiqAI/neuralspotx/commit/27ebedd46b758bde169d282b214afc00de211fe0))


### Documentation

* add agent architecture guidance ([166570a](https://github.com/AmbiqAI/neuralspotx/commit/166570aace8d56533d6aa35f864fabb1aa10a153))
* add google-style python docstrings ([af36b36](https://github.com/AmbiqAI/neuralspotx/commit/af36b36e120666c70e236fff354cb8db9c296b66))
* add repo agent workflow guidance ([#2](https://github.com/AmbiqAI/neuralspotx/issues/2)) ([ca4d7f4](https://github.com/AmbiqAI/neuralspotx/commit/ca4d7f4e575a320859328e6cc1c4c8d10bb7ba16))
