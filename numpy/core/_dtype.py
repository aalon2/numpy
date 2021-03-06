"""
A place for code to be called from the implementation of np.dtype

String handling is much easier to do correctly in python.
"""
from __future__ import division, absolute_import, print_function

import numpy as np


def __str__(dtype):
    if dtype.fields is not None:
        return _struct_str(dtype, include_align=True)
    elif dtype.subdtype:
        return _subarray_str(dtype)
    elif issubclass(dtype.type, np.flexible) or not dtype.isnative:
        return dtype.str
    else:
        return dtype.name


def __repr__(dtype):
    if dtype.fields is not None:
        return _struct_repr(dtype)
    else:
        return "dtype({})".format(_construction_repr(dtype, include_align=True))


def _unpack_field(dtype, offset, title=None):
    """
    Helper function to normalize the items in dtype.fields.

    Call as:

    dtype, offset, title = _unpack_field(*dtype.fields[name])
    """
    return dtype, offset, title


def _isunsized(dtype):
    # PyDataType_ISUNSIZED
    return dtype.itemsize == 0


def _construction_repr(dtype, include_align=False, short=False):
    """
    Creates a string repr of the dtype, excluding the 'dtype()' part
    surrounding the object. This object may be a string, a list, or
    a dict depending on the nature of the dtype. This
    is the object passed as the first parameter to the dtype
    constructor, and if no additional constructor parameters are
    given, will reproduce the exact memory layout.

    Parameters
    ----------
    short : bool
        If true, this creates a shorter repr using 'kind' and 'itemsize', instead
        of the longer type name.

    include_align : bool
        If true, this includes the 'align=True' parameter
        inside the struct dtype construction dict when needed. Use this flag
        if you want a proper repr string without the 'dtype()' part around it.

        If false, this does not preserve the
        'align=True' parameter or sticky NPY_ALIGNED_STRUCT flag for
        struct arrays like the regular repr does, because the 'align'
        flag is not part of first dtype constructor parameter. This
        mode is intended for a full 'repr', where the 'align=True' is
        provided as the second parameter.
    """
    if dtype.fields is not None:
        return _struct_str(dtype, include_align=include_align)
    elif dtype.subdtype:
        return _subarray_str(dtype)


    byteorder = _byte_order_str(dtype)

    if dtype.type == np.bool_:
        if short:
            return "'?'"
        else:
            return "'bool'"

    elif dtype.type == np.object_:
        # The object reference may be different sizes on different
        # platforms, so it should never include the itemsize here.
        return "'O'"

    elif dtype.type == np.string_:
        if _isunsized(dtype):
            return "'S'"
        else:
            return "'S%d'" % dtype.itemsize

    elif dtype.type == np.unicode_:
        if _isunsized(dtype):
            return "'%sU'" % byteorder
        else:
            return "'%sU%d'" % (byteorder, dtype.itemsize / 4)

    elif dtype.type == np.void:
        if _isunsized(dtype):
            return "'V'"
        else:
            return "'V%d'" % dtype.itemsize

    elif dtype.type == np.datetime64:
        return "'%sM8%s'" % (byteorder, _datetime_metadata_str(dtype))

    elif dtype.type == np.timedelta64:
        return "'%sm8%s'" % (byteorder, _datetime_metadata_str(dtype))

    elif np.issubdtype(dtype, np.number):
        # Short repr with endianness, like '<f8'
        if short or dtype.byteorder not in ('=', '|'):
            return "'%s%c%d'" % (byteorder, dtype.kind, dtype.itemsize)

        # Longer repr, like 'float64'
        else:
            kindstrs = {
                'u': "uint",
                'i': "int",
                'f': "float",
                'c': "complex"
            }
            try:
                kindstr = kindstrs[dtype.kind]
            except KeyError:
                raise RuntimeError(
                    "internal dtype repr error, unknown kind {!r}"
                    .format(dtype.kind)
                )
            return "'%s%d'" % (kindstr, 8*dtype.itemsize)

    elif dtype.isbuiltin == 2:
        return dtype.type.__name__

    else:
        raise RuntimeError(
            "Internal error: NumPy dtype unrecognized type number")


def _byte_order_str(dtype):
    """ Normalize byteorder to '<' or '>' """
    # hack to obtain the native and swapped byte order characters
    swapped = np.dtype(int).newbyteorder('s')
    native = swapped.newbyteorder('s')

    byteorder = dtype.byteorder
    if byteorder == '=':
        return native.byteorder
    if byteorder == 's':
        # TODO: this path can never be reached
        return swapped.byteorder
    elif byteorder == '|':
        return ''
    else:
        return byteorder


def _datetime_metadata_str(dtype):
    # This is a hack since the data is not exposed to python in any other way
    return dtype.name[dtype.name.rfind('['):]


def _struct_dict_str(dtype, includealignedflag):
    # unpack the fields dictionary into ls
    names = dtype.names
    fld_dtypes = []
    offsets = []
    titles = []
    for name in names:
        fld_dtype, offset, title = _unpack_field(*dtype.fields[name])
        fld_dtypes.append(fld_dtype)
        offsets.append(offset)
        titles.append(title)

    # Build up a string to make the dictionary

    # First, the names
    ret = "{'names':["
    ret += ",".join(repr(name) for name in names)

    # Second, the formats
    ret += "], 'formats':["
    ret += ",".join(
        _construction_repr(fld_dtype, short=True) for fld_dtype in fld_dtypes)

    # Third, the offsets
    ret += "], 'offsets':["
    ret += ",".join("%d" % offset for offset in offsets)

    # Fourth, the titles
    if any(title is not None for title in titles):
        ret += "], 'titles':["
        ret += ",".join(repr(title) for title in titles)

    # Fifth, the itemsize
    ret += "], 'itemsize':%d" % dtype.itemsize

    if (includealignedflag and dtype.isalignedstruct):
        # Finally, the aligned flag
        ret += ", 'aligned':True}"
    else:
        ret += "}"

    return ret


def _is_packed(dtype):
    """
    Checks whether the structured data type in 'dtype'
    has a simple layout, where all the fields are in order,
    and follow each other with no alignment padding.

    When this returns true, the dtype can be reconstructed
    from a list of the field names and dtypes with no additional
    dtype parameters.

    Duplicates the C `is_dtype_struct_simple_unaligned_layout` functio.
    """
    total_offset = 0
    for name in dtype.names:
        fld_dtype, fld_offset, title = _unpack_field(*dtype.fields[name])
        if fld_offset != total_offset:
            return False
        total_offset += fld_dtype.itemsize
    if total_offset != dtype.itemsize:
        return False
    return True


def _struct_list_str(dtype):
    items = []
    for name in dtype.names:
        fld_dtype, fld_offset, title = _unpack_field(*dtype.fields[name])

        item = "("
        if title is not None:
            item += "({!r}, {!r}), ".format(title, name)
        else:
            item += "{!r}, ".format(name)
        # Special case subarray handling here
        if fld_dtype.subdtype is not None:
            base, shape = fld_dtype.subdtype
            item += "{}, {}".format(
                _construction_repr(base, short=True),
                shape
            )
        else:
            item += _construction_repr(fld_dtype, short=True)

        item += ")"
        items.append(item)

    return "[" + ", ".join(items) + "]"


def _struct_str(dtype, include_align):
    # The list str representation can't include the 'align=' flag,
    # so if it is requested and the struct has the aligned flag set,
    # we must use the dict str instead.
    if not (include_align and dtype.isalignedstruct) and _is_packed(dtype):
        sub = _struct_list_str(dtype)

    else:
        sub = _struct_dict_str(dtype, include_align)

    # If the data type isn't the default, void, show it
    if dtype.type != np.void:
        return "({t.__module__}.{t.__name__}, {f})".format(t=dtype.type, f=sub)
    else:
        return sub


def _subarray_str(dtype):
    base, shape = dtype.subdtype
    return "({}, {})".format(
        _construction_repr(base, short=True),
        shape
    )


def _struct_repr(dtype):
    s = "dtype("
    s += _struct_str(dtype, include_align=False)
    if dtype.isalignedstruct:
        s += ", align=True"
    s += ")"
    return s


