# resnet_example

Tutorial-oriented NSX app scaffold for running the MLPerf Tiny ResNet model on
`apollo510_evb`.

This example intentionally does not commit:

- `model.tflite`
- `golden.npz`
- `src/resnet_sample_data.h`
- `modules/resnet-aot/`

You fetch the model-zoo assets yourself, generate the sample header yourself,
and run `helia-aot` yourself.

## What This Example Contains

- `nsx.yml` with the runtime dependencies needed for the ResNet flow
- `CMakeLists.txt` that links `nsx::resnet_aot` when the generated module is
  present
- `src/main.c` that runs the generated model when both the AOT module and
  generated sample header exist, otherwise prints setup instructions
- `tools/generate_sample_header.py` to convert the model-zoo `golden.npz` file
  into `src/resnet_sample_data.h`

## 1. Fetch The Model-Zoo Assets

```bash
cd neuralspotx/examples/resnet_example

git clone https://github.com/AmbiqAI/helia-model-zoo.git /tmp/helia-model-zoo
cp /tmp/helia-model-zoo/vision/mlperf-tiny/resnet/model.tflite ./model.tflite
cp /tmp/helia-model-zoo/vision/mlperf-tiny/resnet/golden.npz ./golden.npz
```

## 2. Generate The Sample Header

```bash
cd neuralspotx/examples/resnet_example

uv run --with numpy python tools/generate_sample_header.py \
    --golden ./golden.npz \
    --output ./src/resnet_sample_data.h
```

That creates the embedded input/output fixture used by `src/main.c`.

## 3. Run heliaAOT

```bash
cd neuralspotx/examples/resnet_example

uvx --python python3.12 helia-aot convert \
    --model.path ./model.tflite \
    --module.path ./modules \
    --module.type nsx \
    --module.name resnet-aot \
    --module.prefix resnet \
    --platform.name apollo510_evb \
    --force
```

That writes the generated module to `modules/resnet-aot/`.

## 4. Mark The Generated Module As Vendored

Add this entry to `nsx.yml` under `modules:` before you lock/build:

```yaml
- name: resnet-aot
  source:
    vendored: true
```

## 5. Build

```bash
cd neuralspotx/examples/resnet_example
nsx lock --app-dir .
nsx configure --app-dir .
nsx build --app-dir .
```

## 6. Flash And View

```bash
cd neuralspotx/examples/resnet_example
nsx flash --app-dir .
nsx view --app-dir .
```

Expected SWO output includes:

```text
resnet_example: initializing AOT model
input bytes: 3072
output bytes: 10
expected class index: 3 (cat)
predicted class index: 3 (cat)
scores: ...
classification match: PASS
max logit diff vs golden: ...
logit tolerance match (+/-8): PASS
```

## Clean Working Tree

The fetched and generated files are ignored by git so this scaffold can stay in
the repo without tracking model-zoo binaries or AOT output.
