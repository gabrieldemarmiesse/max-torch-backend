import torch
from max.dtype import DType

from max.graph import Graph
from max.torch.torch import max_device_ref
import max.graph.value
from max import engine
from max.driver import Accelerator, accelerator_count, CPU
from .mappings import MAPPING_TORCH_TO_MOJO_FUNCTIONS
import uuid

def get_fully_qualified_name(func):
    return f"{func.__module__}.{func.__qualname__}"

class TensorsBook:
    def __init__(self):
        self.tensors = {}

    def __setitem__(self, name: str, tensor):
        self.tensors[name] = tensor

    def convert_to_max(self, something):
        if isinstance(something, torch.fx.Node):
            return self.tensors[something.name]
        elif isinstance(something, int):
            return something
        elif isinstance(something, torch.fx.immutable_collections.immutable_list):
            return [self.convert_to_max(x) for x in something]
        elif isinstance(something, tuple):
            return tuple(self.convert_to_max(x) for x in something)
        raise ValueError(f"Unsupported type: {type(something)}")


class GraphFunction:
    def __init__(self, gm: torch.fx.GraphModule):
        self.gm = gm

    def __call__(
        self, *args: max.graph.value.TensorValue
    ) -> tuple[max.graph.value.TensorValue, ...]:
        tensor_book = TensorsBook()
        args_index = 0
        for node in self.gm.graph.nodes:
            if node.op == "placeholder":
                tensor_book[node.name] = args[args_index]
                args_index += 1
            elif node.op == "call_function":
                func_args = [tensor_book.convert_to_max(x) for x in node.args]
                func_kwags = {
                    k: tensor_book.convert_to_max(v) for k, v in node.kwargs.items()
                }
                if node.target not in MAPPING_TORCH_TO_MOJO_FUNCTIONS:
                    raise ValueError(
                        f"Function {get_fully_qualified_name(node.target)} not supported by the Max backend yet."
                    )
                tensor = MAPPING_TORCH_TO_MOJO_FUNCTIONS[node.target](
                    *func_args, **func_kwags
                )
                tensor_book[node.name] = tensor
            elif node.op == "output":
                return tuple(tensor_book.convert_to_max(x) for x in node.args[0])


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
                shape.append(str(uuid.uuid4()))
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


class MaxCompiler:
    def __init__(self, gm: torch.fx.GraphModule, example_inputs: list[torch.Tensor]):
        self.gm = gm
        self.example_inputs = example_inputs
        #gm.graph.print_tabular()

        # Use meta tensors (no memory allocation, no computation)
        # Meta tensors only track shape/dtype/device metadata
        meta_inputs = [torch.empty_like(inp, device="meta") for inp in example_inputs]
        with torch.no_grad():
            self.meta_outputs = gm(*meta_inputs)
            if isinstance(self.meta_outputs, torch.Tensor):
                self.meta_outputs = [self.meta_outputs]

        max_input_specs = generate_input_types(example_inputs)
        with Graph("some_graph", input_types=max_input_specs) as graph:
            outputs = GraphFunction(self.gm)(*graph.inputs)
            graph.output(*outputs)

        session = engine.InferenceSession(
            devices=[Accelerator(i) for i in range(accelerator_count())] + [CPU()]
        )
        self.model = session.load(graph)

    def __call__(self, *args) -> list[torch.Tensor]:
        outputs = self.model.execute(*args)
        return [torch.Tensor(x) for x in outputs]
