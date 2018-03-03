import torch
import importlib
import warnings
from collections import defaultdict


def _type(self, new_type=None, non_blocking=False, **kwargs):
    """Returns the type if `new_type` is not provided, else casts this object to
    the specified type.

    If this is already of the correct type, no copy is performed and the
    original object is returned.

    Args:
        new_type (type or string): The desired type
        non_blocking (bool): If ``True``, and the source is in pinned memory
            and destination is on the GPU or vice versa, the copy is performed
            asynchronously with respect to the host. Otherwise, the argument
            has no effect.
        **kwargs: For compatibility, may contain the key ``async`` in place of
            the ``non_blocking`` argument.
    """
    non_blocking = _get_async_or_non_blocking('type', non_blocking, kwargs)
    if new_type is None:
        return self.__module__ + '.' + self.__class__.__name__

    if isinstance(new_type, str):
        new_type = _import_dotted_name(new_type)
    if new_type == type(self):
        return self
    if self.is_sparse:
        if not new_type.is_sparse:
            raise RuntimeError("Cannot cast sparse tensor to dense tensor")
        new_module_name = new_type.__module__.replace('.sparse', '')
        new_values_type_name = new_module_name + '.' + new_type.__name__
        new_values = self._values().type(new_values_type_name, non_blocking)
        new_indices_type_name = new_module_name + '.LongTensor'
        new_indices = self._indices().type(new_indices_type_name, non_blocking)
        return new_type(new_indices, new_values, self.size())
    if new_type.is_sparse:
        raise RuntimeError("Cannot cast dense tensor to sparse tensor")
    return new_type(self.size()).copy_(self, non_blocking)


def _cuda(self, device=None, non_blocking=False, **kwargs):
    """Returns a copy of this object in CUDA memory.

    If this object is already in CUDA memory and on the correct device, then
    no copy is performed and the original object is returned.

    Args:
        device (int): The destination GPU id. Defaults to the current device.
        non_blocking (bool): If ``True`` and the source is in pinned memory,
            the copy will be asynchronous with respect to the host. Otherwise,
            the argument has no effect.
        **kwargs: For compatibility, may contain the key ``async`` in place of
            the ``non_blocking`` argument.
    """
    non_blocking = _get_async_or_non_blocking('cuda', non_blocking, kwargs)
    if self.is_cuda:
        if device is None:
            device = torch.cuda.current_device()
        if self.get_device() == device:
            return self
    else:
        if device is None:
            device = -1
    with torch.cuda.device(device):
        if self.is_sparse:
            new_type = getattr(torch.cuda.sparse, self.__class__.__name__)
            indices = self._indices().cuda(device, non_blocking)
            values = self._values().cuda(device, non_blocking)
            return new_type(indices, values, self.size())
        else:
            new_type = getattr(torch.cuda, self.__class__.__name__)
            return new_type(self.size()).copy_(self, non_blocking)


def _get_async_or_non_blocking(function_name, non_blocking, kwargs):
    if not kwargs:
        return non_blocking
    if len(kwargs) != 1 or 'async' not in kwargs:
        message = "{}() got an unexpected keyword argument '{}'"
        argument = list(kwargs.keys()).pop()
        raise TypeError(message.format(function_name, argument))
    warnings.warn("'async' is deprecated; use 'non_blocking'")
    return kwargs['async']


def _rebuild_tensor(storage, storage_offset, size, stride):
    class_name = storage.__class__.__name__.replace('Storage', 'Tensor')
    module = importlib.import_module(storage.__module__)
    tensor_class = getattr(module, class_name)
    return tensor_class().set_(storage, storage_offset, size, stride)


def _rebuild_tensor_v2(storage, storage_offset, size, stride, requires_grad, backward_hooks):
    tensor = _rebuild_tensor(storage, storage_offset, size, stride)
    tensor.requires_grad = requires_grad
    tensor._backward_hooks = backward_hooks
    return tensor


def _import_dotted_name(name):
    components = name.split('.')
    obj = __import__(components[0])
    for component in components[1:]:
        obj = getattr(obj, component)
    return obj


# Taken from python 3.5 docs
def _accumulate(iterable, fn=lambda x, y: x + y):
    'Return running totals'
    # _accumulate([1,2,3,4,5]) --> 1 3 6 10 15
    # _accumulate([1,2,3,4,5], operator.mul) --> 1 2 6 24 120
    it = iter(iterable)
    try:
        total = next(it)
    except StopIteration:
        return
    yield total
    for element in it:
        total = fn(total, element)
        yield total


def _flatten_dense_tensors(tensors):
    """Flatten dense tensors into a contiguous 1D buffer. Assume tensors are of
    same dense type.

    Since inputs are dense, the resulting tensor will be a concatenated 1D
    buffer. Element-wise operation on this buffer will be equivalent to
    operating individually.

    Arguments:
        tensors (Iterable[Tensor]): dense tensors to flatten.

    Returns:
        A contiguous 1D buffer containing input tensors.
    """
    if len(tensors) == 1:
        return tensors[0].contiguous().view(-1)
    flat = torch.cat([t.contiguous().view(-1) for t in tensors], dim=0)
    return flat


def _flatten_sparse_tensors(tensors):
    """Flatten sparse tensors into two contiguous 1D buffers, one of indices and
    one of values. Assume tensors are of same sparse type.

    Arguments:
        tensors (Iterable[Tensor]): sparse tensors to flatten.

    Returns:
        A tuple of two contiguous 1D buffers, one containing input tensors'
        indices and the other containing the values.
    """
    flat_indices = _flatten_dense_tensors([t._indices() for t in tensors])
    flat_values = _flatten_dense_tensors([t._values() for t in tensors])
    return flat_indices, flat_values


def _unflatten_dense_tensors(flat, tensors):
    """View a flat buffer using the sizes of tensors. Assume that tensors are of
    same dense type, and that flat is given by _flatten_dense_tensors.

    Arguments:
        flat (Tensor): flattened dense tensors to unflatten.
        tensors (Iterable[Tensor]): dense tensors whose sizes will be used to
          unflatten flat.

    Returns:
        Unflattened dense tensors with sizes same as tensors and values from
        flat.
    """
    outputs = []
    offset = 0
    for tensor in tensors:
        numel = tensor.numel()
        outputs.append(flat.narrow(0, offset, numel).view_as(tensor))
        offset += numel
    return tuple(outputs)


def _unflatten_sparse_tensors(flat, tensors):
    """View flat buffer (containing indices and values) using the sizes of
    tensors. Assume that tensors are of same sparse type, and that flat is given
    by _flatten_sparse_tensors.

    Arguments:
        flat (tuple(Tensor, Tensor)): flattened indices and values of sparse
          tensors to unflatten.
        tensors (Iterable[Tensor]): sparse tensors whose sizes will be used to
          unflatten flat.

    Returns:
        Unflattened sparse tensors with sizes same as tensors and values from
        flat.
    """
    flat_indices, flat_values = flat
    indices = _unflatten_dense_tensors(flat_indices, [t._indices() for t in tensors])
    values = _unflatten_dense_tensors(flat_values, [t._values() for t in tensors])
    outputs = []
    for t, i, v in zip(tensors, indices, values):
        outputs.append(t.new(i, v, t.size()))
    return tuple(outputs)


def _reorder_tensors_as(tensors, ordered_tensors):
    """Assume that tensors are of same order as ordered_tensors within their
    types, e.g., from _take_tensors. Reorder them to be of same order as
    ordered_tensors.

    Arguments:
        tensors (Iterable[Tensor]): tensors to be reordered. They should be of
          the same order as ordered_tensors within their own types.
        ordered_tensors (Iterable[Tensor]): tensors whose order will be the
          reference.

    Returns:
        Ordered tuple of tensors with contents from tensors and order of
        ordered_tensors.
    """
    type_dict = defaultdict(list)
    for tensor in tensors:
        type_dict[tensor.type()].append(tensor)
    type_dict = {t: iter(coll) for t, coll in type_dict.items()}
    return tuple(next(type_dict[tensor.type()]) for tensor in ordered_tensors)


def _take_tensors(tensors, size_limit):
    """Group tensors into chunks. This generator yields a chunk at each time,
    each containing tensors of same type up to certain byte limit in total size.

    Args:
        tensors (Sequence): A sequence of tensors to be separated into chunks.
        size_limit (int): The limit of each chunk in bytes.

    Yields:
        Blocks of tensors of same type and within size_limit. The yielded
        tensors are only ordered as the original sequence within its types.
    """
    buf_dict = defaultdict(lambda: [[], 0])
    for tensor in tensors:
        t = tensor.type()
        if tensor.is_sparse:
            indices = tensor._indices()
            values = tensor._values()
            size = indices.numel() * indices.element_size() + values.numel() * values.element_size()
        else:
            size = tensor.numel() * tensor.element_size()
        buf_and_size = buf_dict[t]
        if buf_and_size[1] + size > size_limit and buf_and_size[1] > 0:
            yield buf_and_size[0]
            buf_and_size = buf_dict[t] = [[], 0]
        buf_and_size[0].append(tensor)
        buf_and_size[1] += size
    for buf, _ in buf_dict.values():
        if len(buf) > 0:
            yield buf


def _repeat(self, *sizes):
    r"""Repeats this tensor along the specified dimensions.

    Unlike :meth:`expand`, this function copies the tensor's data.

    Args:
        *sizes (torch.Size or int...): The number of times to repeat this
            tensor along each dimension

    Example:
        >>> x = torch.Tensor([1, 2, 3])
        >>> x.repeat(4, 2)
         1  2  3  1  2  3
         1  2  3  1  2  3
         1  2  3  1  2  3
         1  2  3  1  2  3
        [torch.FloatTensor of size 4x6]
        >>> x.repeat(4, 2, 1).size()
        torch.Size([4, 2, 3])
    """
    # If args == (torch.Size,), then we need to unpack the tuple
    if len(sizes) == 1 and isinstance(sizes[0], torch.Size):
        sizes = sizes[0]

    repeats = list(sizes)

    if len(repeats) < self.dim():
        raise ValueError('Number of dimensions of repeat dims can not be '
                         'smaller than number of dimensions of tensor')

    # Add new leading dimensions to the tensor if the
    # number of target dimensions is larger than the
    # number of source dimensions.
    num_new_dimensions = len(repeats) - self.dim()
    padded_size = [1] * num_new_dimensions + list(self.size())
    target_size = torch.Size([a * b for a, b in zip(padded_size, repeats)])

    xtensor = self.new().set_(self)
    xtensor = xtensor.expand(padded_size)

    result = self.new()
    result.resize_(target_size)
    urtensor = result.new(result)
    for i in range(xtensor.dim()):
        urtensor = urtensor.unfold(i, xtensor.size(i), xtensor.size(i))

    urtensor.copy_(xtensor.expand_as(urtensor))

    return result
