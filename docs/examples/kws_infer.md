---
title: KWS Inference
tier: integrations
capabilities: [ml, tflite, cmsis-nn, helia-rt]
summary: TFLite Micro keyword-spotting inference with CMSIS-NN kernels.
status: tested
boards_tested: [apollo510_evb]
---
--8<-- "examples/kws_infer/README.md"

If you want a step-by-step workflow for compiling your own `.tflite` into an
NSX module with `helia-aot`, see
[Custom Models with heliaAOT](../user-guide/custom-models.md).
