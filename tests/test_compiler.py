import torch
import torch.nn.functional as F
from collections.abc import Callable
from max_torch_backend import MaxCompiler
import pytest
from torch._dynamo import mark_dynamic


def check_functions_are_equivalent(
    fn: Callable,
    device: str | None,
    inputs: list[torch.Tensor],
    fn_compiled: Callable | None = None,
):
    fn_compiled = fn_compiled or torch.compile(backend=MaxCompiler)(fn)
    if device is not None:
        inputs = [input_tensor.to(device) for input_tensor in inputs]

    output_original = fn(*inputs)
    output_compiled = fn_compiled(*inputs)

    assert type(output_original) == type(output_compiled)

    if isinstance(output_original, torch.Tensor):
        output_original = [output_original]
        output_compiled = [output_compiled]

    for original, compiled in zip(output_original, output_compiled):
        assert original.shape == compiled.shape
        assert original.device == compiled.device
        assert original.dtype == compiled.dtype
        assert torch.allclose(original, compiled, rtol=1e-4, atol=1e-5)


def test_basic_addition(device: str):
    def fn(x, y):
        return x + y

    a = torch.randn(3)
    b = torch.randn(3)

    check_functions_are_equivalent(fn, device, [a, b])


def test_operator_add(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x + y

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b])


def test_subtraction(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x - y

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b])


def test_multiplication(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x * y

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b])


def test_division(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x / y

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes) + 1.0  # Avoid division by zero

    check_functions_are_equivalent(fn, device, [a, b])


def test_floor_division(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x // y

    a = torch.randn(tensor_shapes) * 10
    b = torch.randn(tensor_shapes).abs() + 1.0  # Avoid division by zero

    check_functions_are_equivalent(fn, device, [a, b])


def test_power(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x**y

    a = torch.randn(tensor_shapes).abs() + 0.1  # Avoid negative base
    b = torch.randn(tensor_shapes) * 2  # Keep exponent reasonable

    check_functions_are_equivalent(fn, device, [a, b])


def test_modulo(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return x % y

    a = torch.randn(tensor_shapes) * 10
    b = torch.randn(tensor_shapes).abs() + 1.0  # Avoid division by zero

    check_functions_are_equivalent(fn, device, [a, b])


def test_abs(device: str, tensor_shapes: tuple):
    def fn(x):
        return torch.abs(x)

    a = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a])


def test_cos(device: str, tensor_shapes: tuple):
    def fn(x):
        return torch.cos(x)

    a = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a])


def test_sin(device: str, tensor_shapes: tuple):
    def fn(x):
        return torch.sin(x)

    a = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a])


def test_cat(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return torch.cat([x, y], dim=0)

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b])


def test_combination_add_mul(device: str, tensor_shapes: tuple):
    def fn(x, y, z):
        return (x + y) * z

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)
    c = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b, c])


def test_combination_sub_div(device: str, tensor_shapes: tuple):
    def fn(x, y, z):
        return (x - y) / z

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)
    c = torch.randn(tensor_shapes) + 1.0  # Avoid division by zero

    check_functions_are_equivalent(fn, device, [a, b, c])


def test_combination_trig_arithmetic(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return torch.sin(x) + torch.cos(y)

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b])


def test_combination_abs_mul_add(device: str, tensor_shapes: tuple):
    def fn(x, y, z):
        return torch.abs(x) * y + z

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)
    c = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b, c])


def test_combination_pow_mod(device: str, tensor_shapes: tuple):
    def fn(x, y):
        return (x**2) % y

    a = torch.randn(tensor_shapes).abs() + 0.1
    b = torch.randn(tensor_shapes).abs() + 1.0

    check_functions_are_equivalent(fn, device, [a, b])


def test_complex_combination(device: str, tensor_shapes: tuple):
    def fn(x, y, z):
        return torch.abs(torch.sin(x) * y + torch.cos(z))

    a = torch.randn(tensor_shapes)
    b = torch.randn(tensor_shapes)
    c = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a, b, c])


def test_scalar_shapes(device: str):
    def fn(x, y):
        return x + y * 2

    a = torch.randn(())  # Scalar tensor
    b = torch.randn(())

    check_functions_are_equivalent(fn, device, [a, b])


def test_broadcasting_compatible(device: str):
    def fn(x, y):
        return x + y

    a = torch.randn(5, 1)
    b = torch.randn(1, 5)

    check_functions_are_equivalent(fn, device, [a, b])


def test_conv2d_basic(device: str):
    """Test basic conv2d with default parameters"""

    def fn(x, w):
        return F.conv2d(x, w)

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_with_bias(device: str):
    """Test conv2d with bias"""

    def fn(x, w, b):
        return F.conv2d(x, w, b)

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)
    b = torch.randn(out_channels)

    check_functions_are_equivalent(fn, device, [x, w, b])


def test_conv2d_stride_int(device: str):
    """Test conv2d with integer stride"""

    def fn(x, w):
        return F.conv2d(x, w, stride=2)

    batch_size, in_channels, height, width = 2, 3, 16, 16
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_stride_tuple(device: str):
    """Test conv2d with tuple stride"""

    def fn(x, w):
        return F.conv2d(x, w, stride=(2, 3))

    batch_size, in_channels, height, width = 2, 3, 16, 16
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_padding_int(device: str):
    """Test conv2d with integer padding"""

    def fn(x, w):
        return F.conv2d(x, w, padding=1)

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_padding_tuple(device: str):
    """Test conv2d with tuple padding"""

    def fn(x, w):
        return F.conv2d(x, w, padding=(1, 2))

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


@pytest.mark.xfail(reason="Dilation not implemented yet on max")
def test_conv2d_dilation_int(device: str):
    """Test conv2d with integer dilation"""

    def fn(x, w):
        return F.conv2d(x, w, dilation=2)

    batch_size, in_channels, height, width = 2, 3, 16, 16
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


@pytest.mark.xfail(reason="Dilation not implemented yet on max")
def test_conv2d_dilation_tuple(device: str):
    """Test conv2d with tuple dilation"""

    def fn(x, w):
        return F.conv2d(x, w, dilation=(2, 3))

    batch_size, in_channels, height, width = 2, 3, 16, 16
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_all_params(device: str):
    """Test conv2d with all parameters specified"""

    def fn(x, w, b):
        return F.conv2d(x, w, b, stride=2, padding=1, dilation=1)

    batch_size, in_channels, height, width = 2, 3, 16, 16
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)
    b = torch.randn(out_channels)

    check_functions_are_equivalent(fn, device, [x, w, b])


def test_conv2d_1x1_kernel(device: str):
    """Test conv2d with 1x1 kernel (pointwise convolution)"""

    def fn(x, w):
        return F.conv2d(x, w)

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels = 4

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, 1, 1)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_large_kernel(device: str):
    """Test conv2d with larger kernel"""

    def fn(x, w):
        return F.conv2d(x, w, padding=2)

    batch_size, in_channels, height, width = 2, 3, 16, 16
    out_channels, kernel_size = 4, 5

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_asymmetric_kernel(device: str):
    """Test conv2d with asymmetric kernel"""

    def fn(x, w):
        return F.conv2d(x, w, padding=(1, 2))

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels = 4

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, 3, 5)  # 3x5 kernel

    check_functions_are_equivalent(fn, device, [x, w])


@pytest.mark.xfail(reason="Different input sizes not handled yet")
def test_conv2d_different_input_sizes(device: str):
    """Test conv2d with different input tensor sizes"""

    def fn(x, w):
        return F.conv2d(x, w, padding=1)

    # Test various input sizes
    sizes = [(1, 1, 4, 4), (3, 8, 32, 32), (2, 16, 64, 64)]

    for batch_size, in_channels, height, width in sizes:
        out_channels, kernel_size = 4, 3

        x = torch.randn(batch_size, in_channels, height, width)
        w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

        check_functions_are_equivalent(fn, device, [x, w])


def test_conv2d_edge_cases(device: str):
    """Test conv2d edge cases"""

    # Single pixel output
    def fn1(x, w):
        return F.conv2d(x, w)

    batch_size, in_channels = 1, 2
    out_channels, kernel_size = 3, 3

    x = torch.randn(batch_size, in_channels, 3, 3)  # Exactly kernel size
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)

    check_functions_are_equivalent(fn1, device, [x, w])


def test_conv2d_combined_with_other_ops(device: str):
    """Test conv2d combined with other operations"""

    def fn(x, w, b, y):
        conv_out = F.conv2d(x, w, b, padding=1)
        return conv_out + y

    batch_size, in_channels, height, width = 2, 3, 8, 8
    out_channels, kernel_size = 4, 3

    x = torch.randn(batch_size, in_channels, height, width)
    w = torch.randn(out_channels, in_channels, kernel_size, kernel_size)
    b = torch.randn(out_channels)
    # y should have same shape as conv output: (2, 4, 8, 8)
    y = torch.randn(batch_size, out_channels, height, width)

    check_functions_are_equivalent(fn, device, [x, w, b, y])


def test_embedding_basic(device: str):
    """Test basic embedding lookup"""

    def fn(indices, weight):
        return F.embedding(indices, weight)

    vocab_size, embedding_dim = 10, 5
    seq_length = 4

    # Create indices tensor (LongTensor)
    indices = torch.randint(0, vocab_size, (seq_length,))
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight])


def test_embedding_2d_indices(device: str):
    """Test embedding with 2D indices (batch processing)"""

    def fn(indices, weight):
        return F.embedding(indices, weight)

    vocab_size, embedding_dim = 20, 8
    batch_size, seq_length = 3, 6

    indices = torch.randint(0, vocab_size, (batch_size, seq_length))
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight])


def test_embedding_3d_indices(device: str):
    """Test embedding with 3D indices"""

    def fn(indices, weight):
        return F.embedding(indices, weight)

    vocab_size, embedding_dim = 15, 4
    batch_size, seq_length, depth = 2, 3, 4

    indices = torch.randint(0, vocab_size, (batch_size, seq_length, depth))
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight])


def test_embedding_single_index(device: str):
    """Test embedding with single index (scalar)"""

    def fn(indices, weight):
        return F.embedding(indices, weight)

    vocab_size, embedding_dim = 10, 3

    indices = torch.tensor(5)  # Scalar tensor
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight])


def test_embedding_combined_with_other_ops(device: str):
    """Test embedding combined with other operations"""

    def fn(indices, weight, bias):
        embedded = F.embedding(indices, weight)
        return embedded + bias

    vocab_size, embedding_dim = 10, 5
    seq_length = 4

    indices = torch.randint(0, vocab_size, (seq_length,))
    weight = torch.randn(vocab_size, embedding_dim)
    bias = torch.randn(embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight, bias])


def test_embedding_with_padding_idx(device: str):
    """Test embedding with padding_idx parameter"""

    def fn(indices, weight):
        return F.embedding(indices, weight, padding_idx=0)

    vocab_size, embedding_dim = 8, 4

    # Include padding index (0) in the indices
    indices = torch.tensor([[0, 1, 2, 0, 3], [4, 0, 5, 6, 0]])
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight])


def test_embedding_padding_idx_different_values(device: str):
    """Test embedding with different padding_idx values"""

    def fn_pad_0(indices, weight):
        return F.embedding(indices, weight, padding_idx=0)

    def fn_pad_2(indices, weight):
        return F.embedding(indices, weight, padding_idx=2)

    vocab_size, embedding_dim = 6, 3

    indices_0 = torch.tensor([0, 1, 3, 0])  # Using 0 as padding
    indices_2 = torch.tensor([1, 2, 4, 2])  # Using 2 as padding
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn_pad_0, device, [indices_0, weight])
    check_functions_are_equivalent(fn_pad_2, device, [indices_2, weight])


def test_embedding_padding_idx_scalar(device: str):
    """Test embedding with padding_idx on scalar indices"""

    def fn(indices, weight):
        return F.embedding(indices, weight, padding_idx=0)

    vocab_size, embedding_dim = 5, 3

    indices = torch.tensor(0)  # Scalar padding index
    weight = torch.randn(vocab_size, embedding_dim)

    check_functions_are_equivalent(fn, device, [indices, weight])


def test_tensor_slice_basic(device: str):
    def fn(x):
        return x[1:3]  # Basic slice along first dimension

    x = torch.randn(5, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_slice_2d(device: str):
    def fn(x):
        return x[1:3, 0:2]  # Slice along both dimensions

    x = torch.randn(5, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_slice_negative_index(device: str):
    def fn(x):
        return x[-2:]  # Negative slice

    x = torch.randn(5, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_to_float(device: str):
    def fn(x):
        return x.float()

    x = torch.randint(0, 10, (5,))

    check_functions_are_equivalent(fn, device, [x])


def test_expand_basic(device: str):
    """Test basic expand operation"""

    def fn(x):
        return x.expand(3, 4)

    x = torch.randn(1, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_expand_with_negative_one(device: str):
    """Test expand with -1 (keep dimension unchanged)"""

    def fn(x):
        return x.expand(-1, 5)

    x = torch.randn(3, 1)

    check_functions_are_equivalent(fn, device, [x])


def test_expand_multiple_dims(device: str):
    """Test expand on tensor with multiple dimensions"""

    def fn(x):
        return x.expand(2, 3, 4)

    x = torch.randn(1, 1, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_expand_same_size(device: str):
    """Test expand to same size (should be no-op)"""

    def fn(x):
        return x.expand(2, 3)

    x = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_expand_add_dimensions(device: str):
    """Test expand adding new leading dimensions"""

    def fn(x):
        return x.expand(2, 3, 4)

    x = torch.randn(4)  # 1D tensor

    check_functions_are_equivalent(fn, device, [x])


def test_expand_mixed_operations(device: str):
    """Test expand combined with arithmetic operations"""

    def fn(x, y):
        expanded_x = x.expand(2, 3)
        return expanded_x + y

    x = torch.randn(1, 3)
    y = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x, y])


def test_expand_with_scalar_broadcast(device: str):
    """Test expand from scalar dimension"""

    def fn(x):
        return x.expand(5, 5)

    x = torch.randn(1, 1)

    check_functions_are_equivalent(fn, device, [x])


def test_expand_complex_pattern(device: str):
    """Test expand with complex dimension pattern"""

    def fn(x):
        return x.expand(2, -1, 4, -1)

    x = torch.randn(1, 3, 1, 5)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_2d(device: str):
    """Test basic transpose on 2D tensor"""

    def fn(x):
        return x.transpose(0, 1)

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_3d_first_last(device: str):
    """Test transpose swapping first and last dimensions on 3D tensor"""

    def fn(x):
        return x.transpose(0, 2)

    x = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_3d_middle_dims(device: str):
    """Test transpose swapping middle dimensions on 3D tensor"""

    def fn(x):
        return x.transpose(1, 2)

    x = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_negative_dims(device: str):
    """Test transpose with negative dimension indices"""

    def fn(x):
        return x.transpose(-2, -1)

    x = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_same_dim(device: str):
    """Test transpose with same dimension (should be no-op)"""

    def fn(x):
        return x.transpose(1, 1)

    x = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_4d(device: str):
    """Test transpose on 4D tensor"""

    def fn(x):
        return x.transpose(1, 3)

    x = torch.randn(2, 3, 4, 5)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_batch_dimension(device: str):
    """Test transpose involving batch dimension"""

    def fn(x):
        return x.transpose(0, 1)

    x = torch.randn(8, 16, 32)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_with_arithmetic(device: str):
    """Test transpose combined with arithmetic operations"""

    def fn(x, y):
        x_t = x.transpose(0, 1)
        return x_t + y

    x = torch.randn(3, 4)
    y = torch.randn(4, 3)

    check_functions_are_equivalent(fn, device, [x, y])


def test_transpose_multiple_ops(device: str):
    """Test multiple transpose operations"""

    def fn(x):
        # First transpose: (2, 3, 4) -> (2, 4, 3)
        x1 = x.transpose(1, 2)
        # Second transpose: (2, 4, 3) -> (4, 2, 3)
        x2 = x1.transpose(0, 1)
        return x2

    x = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_with_other_methods(device: str):
    """Test transpose combined with other tensor methods"""

    def fn(x):
        x_t = x.transpose(0, 1)
        return x_t.expand(-1, 5, -1)

    x = torch.randn(1, 3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_transpose_scalar_like(device: str):
    """Test transpose on tensor with singleton dimensions"""

    def fn(x):
        return x.transpose(0, 2)

    x = torch.randn(1, 3, 1)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_cos_method(device: str):
    """Test tensor.cos() method"""

    def fn(x):
        return x.cos()

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_sin_method(device: str):
    """Test tensor.sin() method"""

    def fn(x):
        return x.sin()

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_cos_sin_combined(device: str):
    """Test combining tensor.cos() and tensor.sin() methods"""

    def fn(x):
        return x.cos() + x.sin()

    x = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_cos_with_arithmetic(device: str):
    """Test tensor.cos() combined with arithmetic operations"""

    def fn(x, y):
        return x.cos() * y

    x = torch.randn(3, 4)
    y = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x, y])


def test_tensor_sin_with_arithmetic(device: str):
    """Test tensor.sin() combined with arithmetic operations"""

    def fn(x, y):
        return x.sin() - y

    x = torch.randn(3, 4)
    y = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x, y])


def test_tensor_cos_sin_chained(device: str):
    """Test chained tensor.cos().sin() operations"""

    def fn(x):
        return x.cos().sin()

    x = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_trig_with_transpose(device: str):
    """Test tensor trigonometric methods with transpose"""

    def fn(x):
        return x.transpose(0, 1).cos()

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_cos_sin_different_shapes(device: str, tensor_shapes: tuple):
    """Test tensor.cos() and tensor.sin() with different tensor shapes"""

    def fn_cos(x):
        return x.cos()

    def fn_sin(x):
        return x.sin()

    x = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn_cos, device, [x])
    check_functions_are_equivalent(fn_sin, device, [x])


def test_tensor_pow_method(device: str):
    """Test tensor.pow() method"""

    def fn(x, y):
        return x.pow(y)

    x = torch.randn(3, 4).abs() + 0.1  # Avoid negative base
    y = torch.randn(3, 4) * 2  # Keep exponent reasonable

    check_functions_are_equivalent(fn, device, [x, y])


def test_tensor_pow_scalar_exponent(device: str):
    """Test tensor.pow() with scalar exponent"""

    def fn(x):
        return x.pow(2)

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_pow_negative_exponent(device: str):
    """Test tensor.pow() with negative exponent"""

    def fn(x):
        return x.pow(-2)

    x = torch.randn(3, 4).abs() + 1.0  # Avoid division by zero

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_pow_fractional_exponent(device: str):
    """Test tensor.pow() with fractional exponent"""

    def fn(x):
        return x.pow(0.5)  # Square root

    x = torch.randn(3, 4).abs() + 0.1  # Ensure positive for square root

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_pow_with_arithmetic(device: str):
    """Test tensor.pow() combined with arithmetic operations"""

    def fn(x, y, z):
        return x.pow(y) + z

    x = torch.randn(3, 4).abs() + 0.1
    y = torch.randn(3, 4) * 2
    z = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x, y, z])


def test_tensor_pow_chained(device: str):
    """Test chained tensor.pow() operations"""

    def fn(x):
        return x.pow(2).pow(0.5)  # Should be approximately x

    x = torch.randn(3, 4).abs() + 0.1

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_pow_broadcast(device: str):
    """Test tensor.pow() with broadcasting"""

    def fn(x, y):
        return x.pow(y)

    x = torch.randn(3, 4).abs() + 0.1
    y = torch.randn(1, 4) * 2

    check_functions_are_equivalent(fn, device, [x, y])


def test_tensor_pow_different_shapes(device: str, tensor_shapes: tuple):
    """Test tensor.pow() with different tensor shapes"""

    def fn(x):
        return x.pow(2)

    x = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_pow_with_other_methods(device: str):
    """Test tensor.pow() combined with other tensor methods"""

    def fn(x):
        return x.transpose(0, 1).pow(2).cos()

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_change_device_to_cpu(device: str):
    """Test changing device to CPU"""

    def fn(x):
        return x.to("cpu")

    x = torch.randn(1, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_change_device_to_cpu_by_device(device: str):
    """Test changing device to CPU"""

    def fn(x):
        return x.to(torch.device("cpu"))

    x = torch.randn(1, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_change_device_to_cuda(device: str, gpu_available: bool):
    """Test changing device to CUDA"""
    if not gpu_available:
        pytest.skip("CUDA not available")

    def fn(x):
        return x.to("cuda")

    x = torch.randn(1, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_change_device_to_cuda_by_device(device: str, gpu_available: bool):
    """Test changing device to CUDA"""
    if not gpu_available:
        pytest.skip("CUDA not available")

    def fn(x):
        return x.to(torch.device("cuda"))

    x = torch.randn(1, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_to_with_dtype_keyword(device: str):
    """Test tensor.to() with dtype keyword argument"""

    def fn(x):
        return x.to(dtype=torch.float32)

    x = torch.randint(0, 10, (2, 3))

    check_functions_are_equivalent(fn, device, [x])


def test_to_with_device_keyword(device: str):
    """Test tensor.to() with device keyword argument"""

    def fn(x):
        return x.to(device="cpu")

    x = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_to_with_device_dtype_keywords(device: str):
    """Test tensor.to() with both device and dtype keyword arguments"""

    def fn(x):
        return x.to(device="cpu", dtype=torch.float32)

    x = torch.randint(0, 10, (2, 3))

    check_functions_are_equivalent(fn, device, [x])


def test_to_with_torch_device_object(device: str):
    """Test tensor.to() with torch.device object"""

    def fn(x):
        return x.to(torch.device("cpu"))

    x = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_to_with_torch_device_object_cuda(device: str, gpu_available: bool):
    """Test tensor.to() with torch.device object for CUDA"""
    if not gpu_available:
        pytest.skip("CUDA not available")

    def fn(x):
        return x.to(torch.device("cuda:0"))

    x = torch.randn(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_to_with_dtype_positional(device: str):
    """Test tensor.to() with dtype as positional argument"""

    def fn(x):
        return x.to(torch.float32)

    x = torch.randint(0, 10, (2, 3))

    check_functions_are_equivalent(fn, device, [x])


def test_to_dtype_conversion_int_to_float(device: str):
    """Test converting integer tensor to float"""

    def fn(x):
        return x.to(dtype=torch.float32)

    x = torch.randint(-5, 5, (3, 4))

    check_functions_are_equivalent(fn, device, [x])


@pytest.mark.xfail(reason="dtype casting not working correctly in MAX backend")
def test_to_dtype_conversion_float_to_int(device: str):
    """Test converting float tensor to int"""

    def fn(x):
        return x.to(dtype=torch.int32)

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_to_dtype_conversion_double_to_float(device: str):
    """Test converting double tensor to float"""

    def fn(x):
        return x.to(dtype=torch.float32)

    x = torch.randn(3, 4, dtype=torch.float64)

    check_functions_are_equivalent(fn, device, [x])


def test_to_combined_with_operations(device: str):
    """Test tensor.to() combined with other operations"""

    def fn(x, y):
        x_converted = x.to(dtype=torch.float32)
        return x_converted + y

    x = torch.randint(0, 10, (3, 4))
    y = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x, y])


def test_to_device_transfer_with_computation(device: str):
    """Test device transfer followed by computation"""

    def fn(x):
        x_cpu = x.to("cpu")
        return x_cpu * 2

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_autocast_enter_exit():
    """Test autocast enter and exit functionality"""

    def fn(x):
        with torch.amp.autocast("cuda", enabled=True):
            return x + 1.0

    x = torch.randn(2, 3)

    # Test on CPU device only as autocast behavior may vary
    check_functions_are_equivalent(fn, "cpu", [x])


@pytest.mark.xfail(reason="dtype casting not working correctly in MAX backend")
def test_complex_to_operations(device: str):
    """Test complex combinations of .to() operations"""

    def fn(x):
        # Convert to float first, then back to int
        x_float = x.to(dtype=torch.float32)
        result = x_float * 2.5
        return result.to(dtype=torch.int32)

    x = torch.randint(1, 5, (2, 3))

    check_functions_are_equivalent(fn, device, [x])


class MaxCompilerCallCount:
    def __init__(self):
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        return MaxCompiler(*args, **kwargs)


def test_dynamic_shapes(device: str):
    """Testing the behavior with mark_dynamic()."""

    def fn(x, y):
        return x + y

    counter = MaxCompilerCallCount()
    fn_compiled = torch.compile(backend=counter)(fn)

    a = torch.randn(20, 2).to(device)
    b = torch.randn(2).to(device)

    mark_dynamic(a, 0)

    check_functions_are_equivalent(fn, None, [a, b], fn_compiled)

    for i in range(5, 15):
        a = torch.randn(i, 2).to(device)
        b = torch.randn(2).to(device)
        mark_dynamic(a, 0)

        check_functions_are_equivalent(fn, None, [a, b], fn_compiled)
        # Ensure only one instance of the MaxCompiler is created
    assert counter.call_count == 1


def test_recompilation(device: str):
    """Testing the behavior without mark_dynamic()."""

    def fn(x, y):
        return x + y

    counter = MaxCompilerCallCount()
    fn_compiled = torch.compile(backend=counter)(fn)

    a = torch.randn(20, 2).to(device)
    b = torch.randn(2).to(device)

    check_functions_are_equivalent(fn, None, [a, b], fn_compiled)

    a = torch.randn(10, 2).to(device)
    b = torch.randn(2).to(device)

    check_functions_are_equivalent(fn, None, [a, b], fn_compiled)
    # Ensure a second instance of the MaxCompiler is created
    assert counter.call_count == 2

    # TODO: Make it work if called with more shapes (dynamo doesn't recompile)


def test_mean_no_dim(device: str, tensor_shapes: tuple):
    """Test mean without specifying dimensions (reduce all)"""

    def fn(x):
        return torch.mean(x)

    a = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_single_dim(device: str, tensor_shapes: tuple):
    """Test mean with single dimension"""

    def fn(x):
        return torch.mean(x, dim=1)

    a = torch.randn(tensor_shapes) if len(tensor_shapes) > 1 else torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_negative_dim(device: str, tensor_shapes: tuple):
    """Test mean with negative dimension"""

    def fn(x):
        return torch.mean(x, dim=-1)

    a = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_keepdim_true(device: str, tensor_shapes: tuple):
    """Test mean with keepdim=True"""

    def fn(x):
        return torch.mean(x, dim=1, keepdim=True)

    a = torch.randn(tensor_shapes) if len(tensor_shapes) > 1 else torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_multiple_dims(device: str):
    """Test mean with multiple dimensions"""

    def fn(x):
        return torch.mean(x, dim=(1, 2))

    a = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_multiple_dims_keepdim(device: str):
    """Test mean with multiple dimensions and keepdim=True"""

    def fn(x):
        return torch.mean(x, dim=(0, 2), keepdim=True)

    a = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [a])


def test_tensor_mean_method(device: str, tensor_shapes: tuple):
    """Test tensor.mean() method"""

    def fn(x):
        return x.mean()

    a = torch.randn(tensor_shapes)

    check_functions_are_equivalent(fn, device, [a])


def test_tensor_mean_method_with_dim(device: str, tensor_shapes: tuple):
    """Test tensor.mean(dim) method"""

    def fn(x):
        return x.mean(dim=1)

    a = torch.randn(tensor_shapes) if len(tensor_shapes) > 1 else torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_3d_tensor(device: str):
    """Test mean on 3D tensor"""

    def fn(x):
        return torch.mean(x, dim=1)

    a = torch.randn(2, 3, 4)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_3d_tensor_change_dtype(device: str):
    def fn(x):
        return torch.mean(x, dim=1, dtype=torch.float32)

    a = torch.randn(2, 3, 4).to(torch.int32)

    check_functions_are_equivalent(fn, device, [a])


def test_mean_combined_with_arithmetic(device: str, tensor_shapes: tuple):
    """Test mean combined with arithmetic operations"""

    def fn(x, y):
        mean_x = torch.mean(x, dim=-1, keepdim=True)
        return mean_x + y

    a = torch.randn(tensor_shapes)
    # Create y with compatible shape for broadcasting
    if len(tensor_shapes) == 0:
        y = torch.randn(())
    else:
        y_shape = list(tensor_shapes)
        y_shape[-1] = 1  # Make last dimension 1 for broadcasting
        y = torch.randn(y_shape)

    check_functions_are_equivalent(fn, device, [a, y])


def test_rsqrt_function(device: str):
    """Test torch.rsqrt() function"""

    def fn(x):
        return torch.rsqrt(x)

    x = torch.randn(3, 4).abs() + 0.1  # Ensure positive values for rsqrt

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_function(device: str):
    """Test torch.sqrt() function"""

    def fn(x):
        return torch.sqrt(x)

    x = torch.randn(3, 4).abs() + 0.01  # Ensure positive values for sqrt

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_rsqrt_method(device: str):
    """Test tensor.rsqrt() method"""

    def fn(x):
        return x.rsqrt()

    x = torch.randn(3, 4).abs() + 0.1  # Ensure positive values

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_sqrt_method(device: str):
    """Test tensor.sqrt() method"""

    def fn(x):
        return x.sqrt()

    x = torch.randn(3, 4).abs() + 0.01  # Ensure positive values

    check_functions_are_equivalent(fn, device, [x])


def test_rsqrt_different_shapes(device: str, tensor_shapes: tuple):
    """Test rsqrt with different tensor shapes"""

    def fn(x):
        return torch.rsqrt(x)

    x = torch.randn(tensor_shapes).abs() + 0.1

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_different_shapes(device: str, tensor_shapes: tuple):
    """Test sqrt with different tensor shapes"""

    def fn(x):
        return torch.sqrt(x)

    x = torch.randn(tensor_shapes).abs() + 0.01

    check_functions_are_equivalent(fn, device, [x])


def test_rsqrt_with_ones(device: str):
    """Test rsqrt with tensor of ones (should return ones)"""

    def fn(x):
        return torch.rsqrt(x)

    x = torch.ones(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_with_ones(device: str):
    """Test sqrt with tensor of ones (should return ones)"""

    def fn(x):
        return torch.sqrt(x)

    x = torch.ones(2, 3)

    check_functions_are_equivalent(fn, device, [x])


def test_rsqrt_with_powers_of_two(device: str):
    """Test rsqrt with powers of 2 for exact mathematical results"""

    def fn(x):
        return torch.rsqrt(x)

    x = torch.tensor([1.0, 4.0, 16.0, 64.0])  # Powers of 2

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_with_perfect_squares(device: str):
    """Test sqrt with perfect squares for exact mathematical results"""

    def fn(x):
        return torch.sqrt(x)

    x = torch.tensor([1.0, 4.0, 9.0, 16.0, 25.0])  # Perfect squares

    check_functions_are_equivalent(fn, device, [x])


def test_rsqrt_sqrt_relationship(device: str):
    """Test mathematical relationship: rsqrt(x) * sqrt(x) should equal 1"""

    def fn(x):
        return torch.rsqrt(x) * torch.sqrt(x)

    x = torch.randn(3, 4).abs() + 0.1

    check_functions_are_equivalent(fn, device, [x])


def test_rsqrt_combined_with_arithmetic(device: str):
    """Test rsqrt combined with arithmetic operations"""

    def fn(x, y):
        rsqrt_x = torch.rsqrt(x)
        return rsqrt_x + y

    x = torch.randn(3, 4).abs() + 0.1
    y = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x, y])


def test_sqrt_combined_with_arithmetic(device: str):
    """Test sqrt combined with arithmetic operations"""

    def fn(x, y):
        sqrt_x = torch.sqrt(x)
        return sqrt_x * y

    x = torch.randn(3, 4).abs() + 0.01
    y = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x, y])


def test_chained_sqrt_rsqrt_operations(device: str):
    """Test chained sqrt and rsqrt operations"""

    def fn(x):
        # This should approximately equal x (with small numerical errors)
        return torch.sqrt(torch.rsqrt(x)).pow(2)

    x = torch.randn(3, 4).abs() + 0.1

    check_functions_are_equivalent(fn, device, [x])


def test_rsqrt_with_trigonometric_functions(device: str):
    """Test rsqrt combined with trigonometric functions"""

    def fn(x):
        rsqrt_x = torch.rsqrt(x)
        return torch.sin(rsqrt_x)

    x = torch.randn(3, 4).abs() + 0.1

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_with_trigonometric_functions(device: str):
    """Test sqrt combined with trigonometric functions"""

    def fn(x):
        sqrt_x = torch.sqrt(x)
        return torch.cos(sqrt_x)

    x = torch.randn(3, 4).abs() + 0.01

    check_functions_are_equivalent(fn, device, [x])


def test_tensor_methods_chain_sqrt_rsqrt(device: str):
    """Test chaining tensor methods with sqrt and rsqrt"""

    def fn(x):
        return x.abs().sqrt().rsqrt()

    x = torch.randn(3, 4)

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_rsqrt_with_transpose(device: str):
    """Test sqrt and rsqrt with transpose operations"""

    def fn(x):
        x_t = x.transpose(0, 1)
        return torch.sqrt(x_t) + torch.rsqrt(x_t + 0.1)

    x = torch.randn(3, 4).abs() + 0.01

    check_functions_are_equivalent(fn, device, [x])


def test_sqrt_rsqrt_broadcasting(device: str):
    """Test sqrt and rsqrt with broadcasting"""

    def fn(x, y):
        sqrt_x = torch.sqrt(x)
        rsqrt_y = torch.rsqrt(y)
        return sqrt_x + rsqrt_y

    x = torch.randn(3, 1).abs() + 0.01
    y = torch.randn(1, 4).abs() + 0.1

    check_functions_are_equivalent(fn, device, [x, y])
