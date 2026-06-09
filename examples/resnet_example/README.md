# resnet_example

NSX example app that runs the MLPerf Tiny ResNet image classification model on
`apollo510_evb` using a heliaAOT-generated NSX module.

This example is the companion app for the "Custom Models with heliaAOT"
tutorial. It shows the resulting app layout after walking through the full
model-to-module flow yourself.

## App Layout

- `model.tflite` is the copied model artifact from
  `helia-model-zoo/vision/mlperf-tiny/resnet/`.
- `golden.npz` is the Ambiq model-zoo golden fixture containing the model-ready
  input tensor and expected output logits.
- `modules/resnet-aot/` is the vendored heliaAOT-generated NSX module that the
  app links.
- `src/main.c` initializes the generated model, copies the golden input tensor
  into the model input, runs inference once, and checks the output against the
  expected golden classification.

## Golden Input Preview

The source fixture comes from the Ambiq model zoo:

- `helia-model-zoo/vision/mlperf-tiny/resnet/golden.npz`

That fixture stores the model-ready quantized tensor, not the original camera
image file. In this example, class index `3` maps to `cat` under the standard
CIFAR-10 label order used by the MLPerf Tiny ResNet task.

## Regenerate The AOT Module

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

That writes the generated module directly to `modules/resnet-aot/`.

## Build

```bash
cd neuralspotx/examples/resnet_example
nsx lock --app-dir .
nsx configure --app-dir .
nsx build --app-dir .
```

## Flash And View

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
