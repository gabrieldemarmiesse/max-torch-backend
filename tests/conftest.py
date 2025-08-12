import pytest
import torch
from max_torch_backend import (
    get_accelerators,
    MaxCompiler,
    MaxCompilerBackpropCompatible,
)
from max_torch_backend import compiler


@pytest.fixture(params=["cpu", "cuda"])
def device(request, gpu_available: bool):
    device_name = request.param
    if not gpu_available and device_name == "cuda":
        pytest.skip("CUDA not available")
    return device_name


@pytest.fixture
def gpu_available() -> bool:
    return len(list(get_accelerators())) > 1


@pytest.fixture(params=[(3,), (2, 3)])
def tensor_shapes(request):
    return request.param


@pytest.fixture(autouse=True)
def reset_compiler():
    torch.compiler.reset()
    yield


@pytest.fixture(params=[MaxCompiler, MaxCompilerBackpropCompatible], autouse=True)
def compiler_to_use(request):
    compiler.default_compiler = request.param
    yield
