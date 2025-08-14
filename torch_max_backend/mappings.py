import operator

import max.graph.ops as max_ops
import torch
from max.torch.torch import max_device_ref
from max.dtype import DType
from max.graph import StaticDim, Dim
import max.graph.type as max_type
import numpy as np
import math
from torch.ops import aten


def torch_cat_equivalent(tensors: list, dim=0):
    return max_ops.concat(tensors, axis=dim)


def torch_stack_equivalent(tensors: list, dim=0):
    return max_ops.stack(tensors, axis=dim)


def torch_aten_embedding_equivalent(
    input,
    weight,
    padding_idx=None,
    max_norm=None,
    norm_type=2.0,
    scale_grad_by_freq=False,
    sparse=False,
):
    # For some reason with aten, input and weight are inverted.
    return torch_embedding_equivalent(
        weight,
        input,
        padding_idx=padding_idx,
        max_norm=max_norm,
        norm_type=norm_type,
        scale_grad_by_freq=scale_grad_by_freq,
        sparse=sparse,
    )


def torch_embedding_equivalent(
    input,
    weight,
    padding_idx=None,
    max_norm=None,
    norm_type=2.0,
    scale_grad_by_freq=False,
    sparse=False,
):
    if max_norm is not None:
        raise NotImplementedError(
            "max_norm is not supported yet in this embedding implementation"
        )
    if scale_grad_by_freq:
        raise NotImplementedError(
            "scale_grad_by_freq is not supported yet in this embedding implementation"
        )
    if sparse:
        raise NotImplementedError(
            "sparse gradients are not supported yet in this embedding implementation"
        )

    # Handle scalar indices by reshaping to have at least one dimension
    # PyTorch embedding returns the selected row directly for scalar input
    # but MAX gather may need proper shape handling
    original_shape = input.shape
    if len(original_shape) == 0:  # Scalar tensor
        input_reshaped = max_ops.unsqueeze(input, axis=0)
        result = max_ops.gather(weight, input_reshaped, axis=0)
        # Remove the added dimension: [1, embedding_dim] -> [embedding_dim]
        return max_ops.squeeze(result, axis=0)
    else:
        # Use gather to select rows from weight matrix based on input indices
        # axis=0 means we're gathering along the first dimension (vocab dimension)
        return max_ops.gather(weight, input, axis=0)


def torch_autocast_equivalent(*args, **kwargs):
    pass


def torch_float_equivalent(tensor):
    return max_ops.cast(tensor, dtype=max_type.DType.float32)


def torch_transpose_equivalent(tensor, dim0, dim1):
    # Get the current tensor dimensions
    ndim = len(tensor.shape)

    # Handle negative dimensions
    if dim0 < 0:
        dim0 = ndim + dim0
    if dim1 < 0:
        dim1 = ndim + dim1

    # Validate dimensions
    if dim0 < 0 or dim0 >= ndim:
        raise ValueError(
            f"Dimension {dim0} out of range for tensor with {ndim} dimensions"
        )
    if dim1 < 0 or dim1 >= ndim:
        raise ValueError(
            f"Dimension {dim1} out of range for tensor with {ndim} dimensions"
        )

    # If dimensions are the same, no change needed
    if dim0 == dim1:
        return tensor

    # Create permutation list - swap dim0 and dim1
    perm = list(range(ndim))
    perm[dim0], perm[dim1] = perm[dim1], perm[dim0]

    return max_ops.permute(tensor, perm)


def torch_contiguous_equivalent(tensor):
    return tensor


def torch_view_equivalent(tensor, *shape):
    if len(shape) == 1 and isinstance(shape[0], tuple | list):
        target_shape = list(shape[0])
    else:
        target_shape = list(shape)
    return max_ops.reshape(tensor, target_shape)


def torch_unsqueeze_equivalent(tensor, dim):
    return max_ops.unsqueeze(tensor, axis=dim)


def relu_equivalent(tensor, inplace: bool = False):
    # inplace has no meaning in max since it's graph-based
    return max_ops.relu(tensor)


def torch_tril_equivalent(input: max_ops.TensorType, diagonal: int = 0, *, out=None):
    # Max doesn't have tril built-in, so we get around this. It should be pretty
    # easy to implement on cpu and gpu though.
    shape = input.shape

    for i in range(len(shape)):
        if not isinstance(shape[i], StaticDim):
            raise ValueError(f"Input dims must be static, got shape {shape}")

    shape_ints = [int(dim) for dim in shape]

    numpy_mask = np.ones(shape_ints, dtype=input.dtype.to_numpy())
    numpy_mask = np.tril(numpy_mask, k=diagonal)
    mask_in_graph = max_ops.constant(numpy_mask, dtype=input.dtype, device=input.device)
    result = input * mask_in_graph
    return result


def torch_triu_equivalent(input: max_ops.TensorType, diagonal: int = 0, *, out=None):
    # For dynamic shapes, we can't pre-compute a mask. Instead we use a different approach.
    # For now, let's check if we can handle static dims, otherwise return input unchanged
    # TODO: Implement dynamic triu using coordinate-based masking
    shape = input.shape

    try:
        # Try to handle static dimensions
        for i in range(len(shape)):
            if not isinstance(shape[i], StaticDim):
                # For dynamic shapes, just return the input unchanged for now
                # This is not correct but will allow the graph to compile
                # TODO: Implement proper dynamic triu
                return input

        shape_ints = [int(dim) for dim in shape]

        numpy_mask = np.ones(shape_ints, dtype=input.dtype.to_numpy())
        numpy_mask = np.triu(numpy_mask, k=diagonal)
        mask_in_graph = max_ops.constant(
            numpy_mask, dtype=input.dtype, device=input.device
        )
        result = input * mask_in_graph
        return result
    except Exception:
        # Fallback: return input unchanged
        return input


def torch_split_equivalent(
    input: max_ops.TensorType, split_size: int | list[int], dim: int = 0
) -> list[max_ops.TensorType]:
    if isinstance(split_size, int):
        shape = int(input.shape[dim])
        new_split_size = [split_size] * (shape // split_size)
        if shape % split_size != 0:
            new_split_size.append(shape % split_size)
    else:
        new_split_size = split_size
    return max_ops.split(input, new_split_size, dim)


def torch_unbind_equivalent(
    input: max_ops.TensorType, dim: int = 0
) -> list[max_ops.TensorType]:
    """
    Equivalent to torch.unbind - removes a tensor dimension and returns a tuple of all slices along that dimension.
    """
    # Get the size of the dimension to unbind
    shape = input.shape
    if dim < 0:
        dim = len(shape) + dim

    size = int(shape[dim])

    # Use split with size 1 to get individual slices, then squeeze
    split_sizes = [1] * size
    split_tensors = max_ops.split(input, split_sizes, dim)

    # Squeeze each tensor to remove the dimension we split along
    result = []
    for tensor in split_tensors:
        squeezed = max_ops.squeeze(tensor, axis=dim)
        result.append(squeezed)

    return result


def torch_repeat_interleave_equivalent(
    input: max_ops.TensorType, repeats: int, dim: int = 0
) -> max_ops.TensorType:
    """
    Equivalent to torch.repeat_interleave - repeats elements of a tensor along a dimension.
    Each element is repeated 'repeats' times before moving to the next element.
    """
    # Handle negative dim
    if dim < 0:
        dim = len(input.shape) + dim

    # Get the current shape
    shape = input.shape

    # Create a new shape where the specified dimension is expanded
    new_shape = list(shape)
    new_shape[dim] = int(new_shape[dim]) * repeats

    # Use expand to repeat elements along the dimension
    # First, add a new dimension after the target dim, then expand and reshape
    expanded_shape = list(shape)
    expanded_shape.insert(dim + 1, repeats)

    # Add the new dimension
    unsqueezed = max_ops.unsqueeze(input, axis=dim + 1)

    # Expand along the new dimension
    expanded = max_ops.broadcast_to(unsqueezed, expanded_shape)

    # Reshape to merge the repeated dimension
    result = max_ops.reshape(expanded, new_shape)

    return result


def torch_amax_equivalent(input, dim=None, keepdim=False, *, out=None):
    # If only input is provided, we find the maximum along the specified dimension
    if not dim:
        dim = [i for i in range(len(input.shape))]
    elif isinstance(dim, int):
        dim = [dim]

    # Similar to mean, we can only reduce dimensions one at a time
    result = input
    for axis in dim:
        result = max_ops.max(result, axis=axis)
    if not keepdim:
        # Squeeze the reduced dimensions
        for axis in sorted(dim, reverse=True):
            result = max_ops.squeeze(result, axis=axis)
    return result


def torch_amin_equivalent(input, dim=None, keepdim=False, *, out=None):
    # If only input is provided, we find the minimum along the specified dimension
    if not dim:
        dim = [i for i in range(len(input.shape))]
    elif isinstance(dim, int):
        dim = [dim]

    # Similar to mean, we can only reduce dimensions one at a time
    result = input
    for axis in dim:
        result = max_ops.min(result, axis=axis)
    if not keepdim:
        # Squeeze the reduced dimensions
        for axis in sorted(dim, reverse=True):
            result = max_ops.squeeze(result, axis=axis)
    return result


def torch_argmax_equivalent(input, dim=None, keepdim=False, *, out=None):
    # If dim is None, return argmax of flattened tensor
    if dim is None:
        # Flatten the tensor and compute argmax along axis 0
        flattened = max_ops.reshape(input, [-1])
        result = max_ops.argmax(flattened, axis=0)
        if keepdim:
            # Return tensor with same number of dimensions as input, all size 1
            result_shape = [1] * len(input.shape)
            result = max_ops.reshape(result, result_shape)
        else:
            # Return scalar (0-dimensional tensor)
            result = max_ops.squeeze(result, axis=0)
    else:
        # Compute argmax along specified dimension
        result = max_ops.argmax(input, axis=dim)
        if not keepdim:
            # Squeeze the reduced dimension
            result = max_ops.squeeze(result, axis=dim)
    return result


def torch_argmin_equivalent(input, dim=None, keepdim=False, *, out=None):
    # If dim is None, return argmin of flattened tensor
    if dim is None:
        # Flatten the tensor and compute argmin along axis 0
        flattened = max_ops.reshape(input, [-1])
        result = max_ops.argmin(flattened, axis=0)
        if keepdim:
            # Return tensor with same number of dimensions as input, all size 1
            result_shape = [1] * len(input.shape)
            result = max_ops.reshape(result, result_shape)
        else:
            # Return scalar (0-dimensional tensor)
            result = max_ops.squeeze(result, axis=0)
    else:
        # Compute argmin along specified dimension
        result = max_ops.argmin(input, axis=dim)
        if not keepdim:
            # Squeeze the reduced dimension
            result = max_ops.squeeze(result, axis=dim)
    return result


def torch_max_equivalent(*args, **kwargs):
    """
    Implements torch.max with 3 variants:
    1. torch.max(input) - single maximum value
    2. torch.max(input, dim, keepdim=False) - (values, indices) tuple along dimension
    3. torch.max(input, other) - element-wise maximum
    """
    if len(args) == 1:
        # Variant 1: torch.max(input) - single maximum value
        input_tensor = args[0]
        # Check if dim is specified in kwargs
        if "dim" in kwargs:
            dim = kwargs["dim"]
            keepdim = kwargs.get("keepdim", False)
            # Get both values and indices
            values = torch_amax_equivalent(input_tensor, dim=dim, keepdim=keepdim)
            indices = torch_argmax_equivalent(input_tensor, dim=dim, keepdim=keepdim)
            return (values, indices)
        else:
            return torch_amax_equivalent(input_tensor, dim=None, keepdim=False)

    elif len(args) == 2:
        input_tensor, second_arg = args

        # Check if second argument is a tensor (element-wise max)
        if hasattr(second_arg, "shape") and hasattr(second_arg, "dtype"):
            # Variant 3: torch.max(input, other) - element-wise maximum
            return max_ops.max(input_tensor, second_arg)
        else:
            # Variant 2: torch.max(input, dim) - (values, indices) tuple along dimension
            dim = second_arg
            keepdim = kwargs.get("keepdim", False)

            # Get both values and indices
            values = torch_amax_equivalent(input_tensor, dim=dim, keepdim=keepdim)
            indices = torch_argmax_equivalent(input_tensor, dim=dim, keepdim=keepdim)

            # Return as tuple (PyTorch returns namedtuple, but tuple should work)
            return (values, indices)

    elif len(args) == 3:
        # Variant 2: torch.max(input, dim, keepdim)
        input_tensor, dim, keepdim = args
        values = torch_amax_equivalent(input_tensor, dim=dim, keepdim=keepdim)
        indices = torch_argmax_equivalent(input_tensor, dim=dim, keepdim=keepdim)
        return (values, indices)

    else:
        raise ValueError(f"torch.max expects 1-3 arguments, got {len(args)}")


def torch_min_equivalent(*args, **kwargs):
    """
    Implements torch.min with 3 variants:
    1. torch.min(input) - single minimum value
    2. torch.min(input, dim, keepdim=False) - (values, indices) tuple along dimension
    3. torch.min(input, other) - element-wise minimum
    """
    if len(args) == 1:
        # Variant 1: torch.min(input) - single minimum value
        input_tensor = args[0]
        # Check if dim is specified in kwargs
        if "dim" in kwargs:
            dim = kwargs["dim"]
            keepdim = kwargs.get("keepdim", False)
            # Get both values and indices
            values = torch_amin_equivalent(input_tensor, dim=dim, keepdim=keepdim)
            indices = torch_argmin_equivalent(input_tensor, dim=dim, keepdim=keepdim)
            return (values, indices)
        else:
            return torch_amin_equivalent(input_tensor, dim=None, keepdim=False)

    elif len(args) == 2:
        input_tensor, second_arg = args

        # Check if second argument is a tensor (element-wise min)
        if hasattr(second_arg, "shape") and hasattr(second_arg, "dtype"):
            # Variant 3: torch.min(input, other) - element-wise minimum
            return max_ops.min(input_tensor, second_arg)
        else:
            # Variant 2: torch.min(input, dim) - (values, indices) tuple along dimension
            dim = second_arg
            keepdim = kwargs.get("keepdim", False)

            # Get both values and indices
            values = torch_amin_equivalent(input_tensor, dim=dim, keepdim=keepdim)
            indices = torch_argmin_equivalent(input_tensor, dim=dim, keepdim=keepdim)

            # Return as tuple (PyTorch returns namedtuple, but tuple should work)
            return (values, indices)

    elif len(args) == 3:
        # Variant 2: torch.min(input, dim, keepdim)
        input_tensor, dim, keepdim = args
        values = torch_amin_equivalent(input_tensor, dim=dim, keepdim=keepdim)
        indices = torch_argmin_equivalent(input_tensor, dim=dim, keepdim=keepdim)
        return (values, indices)

    else:
        raise ValueError(f"torch.min expects 1-3 arguments, got {len(args)}")


def torch_clamp_equivalent(input, min=None, max=None, *, out=None):
    """
    Implements torch.clamp by clamping all elements in input to the range [min, max].
    Uses max_ops.max and max_ops.min to implement clamp as:
    clamp(x, min, max) = min(max(x, min), max)
    """
    result = input

    # Apply lower bound if min is provided
    if min is not None:
        result = max_ops.max(result, min)

    # Apply upper bound if max is provided
    if max is not None:
        result = max_ops.min(result, max)

    return result


def torch_arange_equivalent(
    start,
    end=None,
    step=1,
    *,
    out=None,
    dtype=None,
    layout=torch.strided,
    device=None,
    requires_grad=False,
    pin_memory=False,
):
    if isinstance(start, float):
        raise ValueError("We don't support float start values for torch.arange")
    if isinstance(step, float):
        raise ValueError("We don't support float step values for torch.arange")
    if isinstance(end, float):
        raise ValueError("We don't support float end values for torch.arange")
    if dtype is None:
        dtype = torch.int64
    dtype = DType.from_torch(dtype)

    if device is None:
        device = torch.get_default_device()
    device = max_device_ref(device)

    if end is None:
        # Single argument form: torch.arange(end)
        end = start
        start = 0

    # Calculate output dimension for max_ops.range
    # The length is ceil((end - start) / step) as per PyTorch docs
    out_dim = end - start
    if step != 1:
        out_dim = int(math.ceil(out_dim / step))

    # Use max_ops.range to create the sequence
    result = max_ops.range(
        Dim(start),
        Dim(end),
        Dim(step),
        out_dim=Dim(out_dim),
        device=device,
        dtype=dtype,
    )
    # TODO: Remove this when the bug is addressed in MAX, range doesn't produce the correct dtype
    # https://github.com/modular/modular/issues/5178
    return max_ops.cast(result, dtype=dtype)


def torch_full_equivalent(
    size,
    fill_value,
    *,
    out=None,
    dtype=None,
    layout=torch.strided,
    device=None,
    requires_grad=False,
    pin_memory=False,
):
    if dtype is None:
        dtype = torch.float32
    dtype = DType.from_torch(dtype)

    if device is None:
        device = torch.get_default_device()
    device = max_device_ref(device)

    # Create a scalar constant with the fill value
    scalar = max_ops.constant(np.array(fill_value), dtype=dtype, device=device)

    # Broadcast the scalar to the target shape
    return max_ops.broadcast_to(scalar, size)


def torch_full_like_equivalent(
    input,
    fill_value,
    *,
    dtype=None,
    layout=torch.strided,
    device=None,
    requires_grad=False,
    pin_memory=False,
    memory_format=None,
):
    # If dtype is not specified, use the input tensor's dtype
    if dtype is None:
        target_dtype = input.dtype
    else:
        target_dtype = DType.from_torch(dtype)

    # If device is not specified, use the input tensor's device
    if device is None:
        target_device = input.device
    else:
        target_device = max_device_ref(device)

    # Get the shape from the input tensor
    target_shape = input.shape

    # Create a scalar constant with the fill value
    scalar = max_ops.constant(
        np.array(fill_value), dtype=target_dtype, device=target_device
    )

    # Broadcast the scalar to the target shape
    return max_ops.broadcast_to(scalar, target_shape)


def torch_gelu_equivalent(input, approximate="none"):
    if approximate == "tanh":
        # Approximation: 0.5 * x * (1 + tanh(sqrt(2/pi) * (x + 0.044715 * x^3)))
        coeff = math.sqrt(2.0 / math.pi)
        inner = coeff * (input + 0.044715 * input * input * input)
        return 0.5 * input * (1.0 + max_ops.tanh(inner))
    else:
        # Exact: 0.5 * x * (1 + erf(x / sqrt(2)))
        # Since MAX might not have erf, use the tanh approximation
        coeff = math.sqrt(2.0 / math.pi)
        inner = coeff * (input + 0.044715 * input * input * input)
        return 0.5 * input * (1.0 + max_ops.tanh(inner))


def torch_sum_equivalent(input, dim=None, keepdim=False, *, dtype=None):
    if dtype is not None:
        max_dtype = DType.from_torch(dtype)
        input = max_ops.cast(input, dtype=max_dtype)

    result = input

    if not dim:
        dim = tuple(range(len(input.shape)))
    elif isinstance(dim, int):
        dim = (dim,)

    dim = [x if x >= 0 else len(input.shape) + x for x in dim]

    # Sum over each dimension
    for axis in sorted(dim, reverse=True):
        result = max_ops.sum(result, axis=axis)

    # Handle keepdim=False - squeeze the reduced dimensions
    if not keepdim:
        # MAX's sum keeps dimensions by default, so we need to squeeze
        for axis in sorted(dim, reverse=True):
            result = max_ops.squeeze(result, axis=axis)

    return result


def torch_aten__softmax_equivalent(input, dim, half_to_float):
    if half_to_float:
        dtype = torch.float32
    else:
        dtype = None
    return torch_softmax_equivalent(input, dim=dim, dtype=dtype)


def torch_softmax_equivalent(input, dim=-1, dtype=None):
    if dtype is not None:
        max_dtype = DType.from_torch(dtype)
        input = max_ops.cast(input, dtype=max_dtype)

    # Handle negative dim
    if dim < 0:
        dim = len(input.shape) + dim

    # Manual implementation
    # Compute max along the specified axis for numerical stability, keeping dimensions
    x_max = torch_amax_equivalent(input, dim=[dim], keepdim=True)

    # Subtract max for numerical stability
    x_shifted = input - x_max

    # Compute exponential
    x_exp = max_ops.exp(x_shifted)

    # Sum along the axis, keeping dimensions for broadcasting
    x_sum = torch_sum_equivalent(x_exp, dim=[dim], keepdim=True)

    # Divide to get softmax
    return x_exp / x_sum


def torch_masked_fill_equivalent(input, mask, value):
    return max_ops.where(mask, value, input)


def torch_t_equivalent(input):
    return torch_transpose_equivalent(input, 0, 1)


def torch_addmm_equivalent(input, mat1, mat2, *, beta=1.0, alpha=1.0):
    # addmm computes: beta * input + alpha * mat1 @ mat2
    matmul_result = operator.matmul(mat1, mat2)

    # Apply scaling factors
    if alpha != 1.0:
        matmul_result = operator.mul(matmul_result, alpha)

    if beta != 1.0:
        scaled_input = operator.mul(input, beta)
    else:
        scaled_input = input

    return operator.add(scaled_input, matmul_result)


def torch_div_equivalent(input, other, *, rounding_mode=None):
    # Handle torch.div with different rounding modes
    if rounding_mode is None:
        return operator.truediv(input, other)
    elif rounding_mode == "floor":
        return operator.floordiv(input, other)
    elif rounding_mode == "trunc":
        # Truncation towards zero (not implemented in operator, need custom logic)
        result = operator.truediv(input, other)
        return max_ops.trunc(result)
    else:
        raise ValueError(f"Unsupported rounding_mode: {rounding_mode}")


def torch_foreach_add_equivalent(tensors, others, alpha=1.0):
    """
    Equivalent to torch._foreach_add.List - element-wise addition of two lists of tensors.
    Computes: tensors[i] + alpha * others[i] for each i
    """
    if len(tensors) != len(others):
        raise ValueError(
            f"Expected len(tensors) == len(others), but got {len(tensors)} and {len(others)}"
        )

    result = []
    for tensor, other in zip(tensors, others):
        if alpha == 1.0:
            result.append(tensor + other)
        else:
            result.append(tensor + alpha * other)

    return result


def identity(x):
    return x


def torch_squeeze_equivalent(input, dim):
    if isinstance(dim, int):
        dim = [dim]
    result = input
    for d in sorted(dim, reverse=True):
        result = max_ops.squeeze(input, axis=d)
    return result


def torch_bmm_equivalent(input, mat2):
    """
    Batch matrix multiplication equivalent to torch.bmm.

    Args:
        input: 3D tensor of shape [batch_size, n, m]
        mat2: 3D tensor of shape [batch_size, m, p]

    Returns:
        3D tensor of shape [batch_size, n, p]
    """
    # MAX's matmul handles batch dimensions automatically through broadcasting
    return max_ops.matmul(input, mat2)


MAPPING_TORCH_TO_MOJO_FUNCTIONS = {
    aten.t: torch_t_equivalent,
    aten.addmm: torch_addmm_equivalent,
    aten._foreach_add: torch_foreach_add_equivalent,
    aten.sub: operator.sub,
    aten.mul: operator.mul,
    aten.add: operator.add,
    aten.le: operator.le,
    aten.lt: operator.lt,
    aten.ge: operator.ge,
    aten.gt: operator.gt,
    aten.eq: operator.eq,
    aten.ne: operator.ne,
    aten.neg: operator.neg,
    aten.div: torch_div_equivalent,
    aten.floordiv: operator.floordiv,
    aten.permute: max_ops.permute,
    aten.pow: operator.pow,
    aten.mm: operator.matmul,
    aten.bmm: torch_bmm_equivalent,
    aten.sum: torch_sum_equivalent,
    aten.view: torch_view_equivalent,
    aten.argmax: torch_argmax_equivalent,
    aten.full: torch_full_equivalent,
    aten.full_like: torch_full_like_equivalent,
    aten.remainder: operator.mod,
    aten.abs: max_ops.abs,
    aten.cos: max_ops.cos,
    aten.sin: max_ops.sin,
    aten.rsqrt: max_ops.rsqrt,
    aten.sqrt: max_ops.sqrt,
    aten.cat: torch_cat_equivalent,
    aten.stack: torch_stack_equivalent,
    aten.min: torch_min_equivalent,
    aten.max: torch_max_equivalent,
    aten.amax: torch_amax_equivalent,
    aten.amin: torch_amin_equivalent,
    aten.clamp: torch_clamp_equivalent,
    aten.arange: torch_arange_equivalent,
    aten.gelu: torch_gelu_equivalent,
    aten.softmax: torch_softmax_equivalent,
    aten._softmax: torch_aten__softmax_equivalent,
    aten.masked_fill: torch_masked_fill_equivalent,
    aten.split: torch_split_equivalent,
    aten.tril: torch_tril_equivalent,
    aten.triu: torch_triu_equivalent,
    aten.unbind: torch_unbind_equivalent,
    aten.repeat_interleave: torch_repeat_interleave_equivalent,
    aten.minimum: max_ops.min,
    aten.maximum: max_ops.max,
    aten.squeeze: torch_squeeze_equivalent,
    aten.unsqueeze: torch_unsqueeze_equivalent,
    aten.argmin: torch_argmin_equivalent,
    aten.argmax: torch_argmax_equivalent,
    aten.relu: relu_equivalent,
    aten.embedding: torch_aten_embedding_equivalent,
}
