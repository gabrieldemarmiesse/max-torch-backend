import torch
from max.dtype import DType

from max.graph import Graph
from max.torch.torch import max_device_ref
import max.graph.value
from max import engine
from max.driver import Accelerator, accelerator_count, CPU
from .mappings import MAPPING_TORCH_TO_MOJO_FUNCTIONS
import uuid
import warnings
from torch._dynamo.backends.common import aot_autograd

from max.graph import DeviceRef
from functorch.compile import make_boxed_func
from torch._decomp import core_aten_decompositions
from torch.fx.experimental.proxy_tensor import make_fx


class MaxCompilerError(Exception):
    pass


def apply_decompositions(gm: torch.fx.GraphModule) -> torch.fx.GraphModule:
    """
    Apply decompositions to any unsupported operations using PyTorch's make_fx.
    This is a generic solution that works for any operation in core_aten_decompositions.
    """
    decomposition_table = core_aten_decompositions()
    # Check if any nodes need decomposition
    needs_decomposition = any(
        node.op == "call_function" and node.target in decomposition_table
        for node in gm.graph.nodes
    )

    if not needs_decomposition:
        return gm

    print("Applying decompositions to unsupported operations...")

    # Create a wrapper function that applies decompositions using make_fx
    def decompose_with_make_fx(*args):
        # We need to create a function that represents the entire graph
        # and then apply decompositions to it
        return gm(*args)

    # Get example inputs from the first few placeholder nodes
    example_inputs = []
    for node in gm.graph.nodes:
        if node.op == "placeholder":
            if "val" in node.meta:
                example_value = node.meta["val"]
            elif "example_value" in node.meta:
                example_value = node.meta["example_value"]
            else:
                # Create a dummy tensor - this might not work for all cases
                example_value = torch.tensor(0.0)

            if isinstance(example_value, torch.Tensor):
                # Use the exact same shape as the original to avoid shape mismatches
                dummy_tensor = torch.zeros_like(example_value)
                example_inputs.append(dummy_tensor)
            else:
                example_inputs.append(example_value)

    # Apply decompositions using make_fx
    decomposed_gm = make_fx(
        decompose_with_make_fx, decomposition_table=decomposition_table
    )(*example_inputs)
    print("Decomposition successful!")
    print("Decomposed graph:")
    decomposed_gm.graph.print_tabular()
    return decomposed_gm


def analyze_dynamic_shapes(example_inputs):
    for i, inp in enumerate(example_inputs):
        if isinstance(inp, torch.SymInt):
            print(f"Input {i} is a symbolic integer: {inp}")
        if hasattr(inp, "_dynamo_dynamic_indices"):
            for dim_idx in inp._dynamo_dynamic_indices:
                print(f"Input {i} Dynamic dimension at index {dim_idx} for input {inp}")


def get_fully_qualified_name(func):
    if isinstance(func, str):
        return f"torch.Tensor.{func}"
    result = ""
    if hasattr(func, "__module__"):
        result += func.__module__ + "."

    if hasattr(func, "__qualname__"):
        result += func.__qualname__

    result += " of type " + str(type(func)) + " "
    return result


def keep_only_tensors(inputs: list, detach: bool = False) -> list[torch.Tensor]:
    result = []
    for x in inputs:
        if isinstance(x, torch.Tensor):
            if detach:
                x = x.detach()
            result.append(x)
    return result


class TensorsBook:
    def __init__(self):
        self.tensors = {}

    def __setitem__(self, name: str, tensor):
        self.tensors[name] = tensor

    def convert_to_max(self, something):
        if isinstance(something, torch.fx.Node):
            return self.tensors[something.name]
        elif isinstance(something, str):
            return something
        elif isinstance(something, int):
            return something
        elif isinstance(something, float):
            return something
        elif isinstance(something, slice):
            return slice(
                self.convert_to_max(something.start),
                self.convert_to_max(something.stop),
                self.convert_to_max(something.step),
            )
        elif isinstance(something, torch.fx.immutable_collections.immutable_list):
            return [self.convert_to_max(x) for x in something]
        elif isinstance(something, tuple):
            return tuple(self.convert_to_max(x) for x in something)
        elif isinstance(something, torch.device):
            return something
        elif isinstance(something, torch.dtype):
            return something
        elif something is None:
            return None
        elif something == ...:
            return ...
        elif isinstance(something, torch.nn.Module):
            return something
        raise ValueError(f"Unsupported type when reading the graph: {type(something)}")


def fetch_attr(gm: torch.fx.GraphModule, target: str):
    """Fetch an attribute from the Module hierarchy of self.gm.
    Args:
        target (str): The fully-qualified name of the attribute to fetch
    """
    target_atoms = target.split(".")
    attr_itr = gm
    for i, atom in enumerate(target_atoms):
        if not hasattr(attr_itr, atom):
            raise RuntimeError(
                f"Node referenced nonexistent target {'.'.join(target_atoms[: i + 1])}"
            )
        attr_itr = getattr(attr_itr, atom)
    return attr_itr


class _GraphFactory:
    def __init__(self):
        self.names_to_input_idx: dict[str, int] = {}
        self.shape_names_to_input_dim: dict[str, tuple[str, int]] = {}
        self.graph_inputs = []
        self.graph = None
        self.tensor_book = TensorsBook()

    def initialize_graph(self):
        if self.graph is not None:
            raise RuntimeError("Graph has already been initialized.")
        self.graph = Graph(
            "max_torch_backend", input_types=self.graph_inputs
        ).__enter__()
        # Let's fill the tensor book
        for tensor_name, idx in self.names_to_input_idx.items():
            self.tensor_book[tensor_name] = self.graph.inputs[idx]
        for shape_name, (tensor_name, dim_idx) in self.shape_names_to_input_dim.items():
            self.tensor_book[shape_name] = self.tensor_book.tensors[tensor_name].shape[
                dim_idx
            ]

    def handle_placeholder(self, node: torch.fx.Node):
        if "example_value" in node.meta:
            example_value = node.meta["example_value"]
        elif "val" in node.meta:
            example_value = node.meta["val"]
        if isinstance(example_value, torch.SymInt):
            pass
        if isinstance(example_value, torch.Tensor | torch.nn.Parameter):
            shape = []
            for dim_idx, dim in enumerate(example_value.shape):
                if isinstance(dim, torch.SymInt):
                    shape.append(str(dim))
                    self.shape_names_to_input_dim[str(dim)] = (node.name, dim_idx)
                elif isinstance(dim, int):
                    shape.append(dim)
                else:
                    raise TypeError(
                        f"Unsupported dimension type {type(dim)} for input {node.name} at index {dim_idx}"
                    )
            self.graph_inputs.append(
                max.graph.value.TensorType(
                    dtype=DType.from_torch(example_value.dtype),
                    shape=shape,
                    device=max_device_ref(example_value.device),
                )
            )
            self.names_to_input_idx[node.name] = len(self.graph_inputs) - 1

    def handle_call_function(self, node_idx: int, node: torch.fx.Node):
        func_args = [self.tensor_book.convert_to_max(x) for x in node.args]
        func_kwargs = {
            k: self.tensor_book.convert_to_max(v) for k, v in node.kwargs.items()
        }
        key = node.target
        if hasattr(key, "namespace") and key.namespace == "aten":
            key = key.overloadpacket

        if key not in MAPPING_TORCH_TO_MOJO_FUNCTIONS:
            raise ValueError(
                f"Failing at node {node_idx}. Function {get_fully_qualified_name(node.target)}  not supported by the Max backend yet."
            )

        try:
            func_output = MAPPING_TORCH_TO_MOJO_FUNCTIONS[key](
                *func_args, **func_kwargs
            )
        except RuntimeError as e:
            raise MaxCompilerError(
                f"Failed to execute node {node_idx} with target {get_fully_qualified_name(node.target)}, "
                f"inputs were: args={func_args}, kwargs={func_kwargs}. Error: {e}. It comes from there in your code: \n"
                f"{node.stack_trace}"
            ) from e
        self.tensor_book[node.name] = func_output

    def handle_get_attr(self, node: torch.fx.Node):
        attr_value = self.fetch_attr(node.target)
        self.tensor_book[node.name] = attr_value

    def handle_output(self, node: torch.fx.Node):
        # Handle both tensor and None outputs (common in backward pass)
        output_tensors = []
        none_indices = []

        for i, x in enumerate(node.args[0]):
            converted = self.tensor_book.convert_to_max(x)
            if converted is None:
                none_indices.append(i)
            else:
                output_tensors.append(converted)

        # Store the none indices for runtime handling
        self.none_indices = none_indices

        if output_tensors:  # Only output if we have actual tensors
            self.graph.output(*output_tensors)
        else:
            raise ValueError(
                f"Node {node.name} has no valid outputs. All outputs were None."
            )

        self.graph.__exit__(None, None, None)

    def create_graph(self, gm: torch.fx.GraphModule) -> Graph:
        # First, apply decompositions to transform unsupported operations
        decomposed_gm = gm

        for node_idx, node in enumerate(decomposed_gm.graph.nodes):
            if node.op == "placeholder":
                self.handle_placeholder(node)
                continue

            if not self.graph:
                self.initialize_graph()

            if node.op in ("call_function", "call_method"):
                self.handle_call_function(node_idx, node)
            elif node.op == "get_attr":
                self.handle_get_attr(node)
            elif node.op == "output":
                self.handle_output(node)
            else:
                raise ValueError(f"Unsupported node type: {node.op}")
        return self.graph


def generate_input_types(
    example_inputs: list[torch.Tensor],
) -> list[max.graph.value.TensorType]:
    result = []
    for inp in example_inputs:
        if not isinstance(inp, torch.Tensor):
            continue
        shape = []
        for dim_idx, dim in enumerate(inp.shape):
            if dim_idx in getattr(inp, "_dynamo_dynamic_indices", {}):
                shape.append("a" + str(uuid.uuid4()).replace("-", "_"))
            else:
                shape.append(int(dim))
        result.append(
            max.graph.value.TensorType(
                dtype=DType.from_torch(inp.dtype),
                shape=shape,
                device=max_device_ref(inp.device),
            )
        )
    return result


def get_accelerators():
    yield CPU()
    if accelerator_count() > 0:
        for i in range(accelerator_count()):
            try:
                yield Accelerator(i)
            except ValueError as e:
                warnings.warn(f"Failed to create accelerator {i}. {e}")


def deviceref_to_torch(device_ref: DeviceRef) -> torch.device:
    """Returns the equivalent PyTorch device for a MAX graph device."""
    if device_ref.api == "cpu":
        return torch.device(f"cpu:{device_ref.id}")
    elif device_ref.api == "cuda":
        return torch.device(f"cuda:{device_ref.id}")
    else:
        raise TypeError(f"Unable to convert {device_ref} to a PyTorch device.")


class MaxCompiler:
    def __init__(
        self, gm: torch.fx.GraphModule, example_inputs: list[torch.Tensor], mode=None
    ):
        self.example_inputs = example_inputs
        gm = apply_decompositions(gm)

        gm.graph.print_tabular()
        # analyze_dynamic_shapes(example_inputs)
        # print(f"number of nodes: {len(gm.graph.nodes)}")
        # print(f"Number of inputs for the examples: {len(example_inputs)}")

        # max_input_specs = generate_input_types(keep_only_tensors(example_inputs))
        ## print(f"max_input_specs: {max_input_specs}")
        # with Graph("some_graph", input_types=max_input_specs) as graph:
        #    outputs = GraphFunction(self.gm)(*graph.inputs)
        #    graph.output(*outputs)
        factory = _GraphFactory()
        graph = factory.create_graph(gm)

        # Store none_indices from the factory
        self.none_indices = getattr(factory, "none_indices", [])

        session = engine.InferenceSession(devices=list(get_accelerators()))
        self.model = session.load(graph)

    def __call__(self, *args) -> list[torch.Tensor]:
        # Detach tensors to avoid gradient tracking issues with DLpack
        outputs = self.model.execute(*keep_only_tensors(args, detach=True))
        tensor_outputs = [torch.from_dlpack(x) for x in outputs]

        # Reconstruct the original output structure with None values
        if hasattr(self, "none_indices") and self.none_indices:
            result = []
            tensor_idx = 0
            for i in range(len(tensor_outputs) + len(self.none_indices)):
                if i in self.none_indices:
                    result.append(None)
                else:
                    result.append(tensor_outputs[tensor_idx])
                    tensor_idx += 1
            return result
        else:
            return tensor_outputs


def _MaxCompilerGradCompatible(
    gm: torch.fx.GraphModule, example_inputs: list[torch.Tensor], mode=None
):
    _max_compiler = MaxCompiler(gm, example_inputs)
    return make_boxed_func(_max_compiler.__call__)


MaxCompilerGradCompatible = aot_autograd(fw_compiler=_MaxCompilerGradCompatible)
