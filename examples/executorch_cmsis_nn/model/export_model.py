#!/usr/bin/env python3

from pathlib import Path

import torch
from executorch.backends.cortex_m.passes.cortex_m_pass_manager import CortexMPassManager
from executorch.backends.cortex_m.quantizer.quantizer import CortexMQuantizer
from executorch.backends.cortex_m.target_config import CortexM, CortexMTargetConfig
from executorch.exir import EdgeCompileConfig, ExecutorchBackendConfig, to_edge
from executorch.exir.dialects._ops import ops as exir_ops
from torch import nn
from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e


class ValidationConv2d(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(2, 4, 3, bias=False)
        with torch.no_grad():
            self.conv.weight.fill_(1.0)

    def forward(self, input_tensor: torch.Tensor) -> torch.Tensor:
        return self.conv(input_tensor)


def remove_unused_export_guards(graph_module: torch.fx.GraphModule) -> None:
    for node in list(graph_module.graph.nodes):
        if node.op == "call_module" and node.target == "_guards_fn":
            if node.users:
                raise RuntimeError("Refusing to remove an export guard with users")
            graph_module.graph.erase_node(node)
            graph_module.delete_submodule("_guards_fn")
    graph_module.recompile()


def channels_last_values(tensor: torch.Tensor) -> list[float]:
    return tensor.detach().permute(0, 2, 3, 1).contiguous().flatten().tolist()


def cpp_float(value: float) -> str:
    rendered = f"{value:.9g}"
    if "." not in rendered and "e" not in rendered:
        rendered += ".0"
    return f"{rendered}F"


def write_validation_header(
    path: Path,
    input_values: list[float],
    expected_values: list[float],
    tolerance: float,
) -> None:
    def array(name: str, values: list[float]) -> str:
        lines = []
        for offset in range(0, len(values), 6):
            row = ", ".join(cpp_float(value) for value in values[offset : offset + 6])
            lines.append(f"    {row},")
        return (
            f"inline constexpr float {name}[{len(values)}] = {{\n"
            + "\n".join(lines)
            + "\n};"
        )

    content = f"""#pragma once

#include <cstddef>

namespace executorch_cmsis_nn_validation {{

inline constexpr std::size_t kInputElementCount = {len(input_values)};
inline constexpr std::size_t kOutputElementCount = {len(expected_values)};
inline constexpr float kTolerance = {cpp_float(tolerance)};

{array("kInput", input_values)}

{array("kExpectedOutput", expected_values)}

}}  // namespace executorch_cmsis_nn_validation
"""
    path.write_text(content, encoding="utf-8")


def main() -> None:
    app_root = Path(__file__).resolve().parent.parent
    pte_path = app_root / "model" / "conv2d_cmsis_nn.pte"
    header_path = app_root / "src" / "validation_data.h"

    torch.manual_seed(0)
    model = ValidationConv2d().eval()
    example_input = (
        torch.linspace(1.0, 5.0, 50, dtype=torch.float32)
        .reshape(1, 2, 5, 5)
        .to(memory_format=torch.channels_last)
    )

    captured = torch.export.export(model, (example_input,), strict=True).module()
    remove_unused_export_guards(captured)
    prepared = prepare_pt2e(captured, CortexMQuantizer())
    with torch.no_grad():
        for scale in (0.25, 0.5, 0.75, 1.0):
            prepared(example_input * scale)
    quantized = convert_pt2e(prepared)
    with torch.no_grad():
        reference_output = quantized(example_input)

    quantized_program = torch.export.export(quantized, (example_input,), strict=True)
    edge_config = EdgeCompileConfig(_check_ir_validity=False)
    edge_program = to_edge(quantized_program, compile_config=edge_config)
    transformed = CortexMPassManager(
        edge_program.exported_program(),
        target_config=CortexMTargetConfig(cpu=CortexM.M55),
    ).transform()
    edge_program._edge_programs["forward"] = transformed

    expected_ops = (
        exir_ops.edge.cortex_m.quantize_per_tensor.default,
        exir_ops.edge.cortex_m.quantized_conv2d.default,
        exir_ops.edge.cortex_m.dequantize_per_tensor.default,
    )
    actual_ops = [
        node.target
        for node in transformed.graph_module.graph.nodes
        if node.op == "call_function"
    ]
    for expected_op in expected_ops:
        if actual_ops.count(expected_op) != 1:
            raise RuntimeError(
                f"Expected one {expected_op}, transformed graph has {actual_ops}"
            )
    if len(actual_ops) != len(expected_ops):
        raise RuntimeError(f"Unexpected operators in transformed graph: {actual_ops}")

    dequantize_node = next(
        node
        for node in transformed.graph_module.graph.nodes
        if node.target == exir_ops.edge.cortex_m.dequantize_per_tensor.default
    )
    output_scale = float(dequantize_node.args[1])
    tolerance = 2.0 * output_scale + 1.0e-6

    executorch_program = edge_program.to_executorch(
        config=ExecutorchBackendConfig(extract_delegate_segments=False)
    )
    pte_path.write_bytes(executorch_program.buffer)
    write_validation_header(
        header_path,
        channels_last_values(example_input),
        channels_last_values(reference_output),
        tolerance,
    )

    print(f"Wrote {pte_path} ({pte_path.stat().st_size} bytes)")
    print(f"Wrote {header_path}")
    print("Validated operators:")
    for operator in actual_ops:
        print(f"  {operator}")
    print(f"Output tolerance: {tolerance:.9g}")


if __name__ == "__main__":
    main()
