# Changelog

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
