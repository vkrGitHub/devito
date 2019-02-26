import sympy

from cached_property import cached_property

from devito.finite_differences import Differentiable, generate_fd_shortcuts
from devito.types.basic import AbstractCachedFunction
from devito.types.dense import Function


class VectorFunction(sympy.MatrixSymbol):
    """
    Discretized symbol representing an array in symbolic equations.

    A Function carries multi-dimensional data and provides operations to create
    finite-differences approximations.

    A Function encapsulates space-varying data; for data that also varies in time,
    use TimeFunction instead.

    Parameters
    ----------
    name : str
        Name of the symbol.
    grid : Grid, optional
        Carries shape, dimensions, and dtype of the Function. When grid is not
        provided, shape and dimensions must be given. For MPI execution, a
        Grid is compulsory.
    space_order : int or 3-tuple of ints, optional
        Discretisation order for space derivatives. Defaults to 1. ``space_order`` also
        impacts the number of points available around a generic point of interest.  By
        default, ``space_order`` points are available on both sides of a generic point of
        interest, including those nearby the grid boundary. Sometimes, fewer points
        suffice; in other scenarios, more points are necessary. In such cases, instead of
        an integer, one can pass a 3-tuple ``(o, lp, rp)`` indicating the discretization
        order (``o``) as well as the number of points on the left (``lp``) and right
        (``rp``) sides of a generic point of interest.
    shape : tuple of ints, optional
        Shape of the domain region in grid points. Only necessary if ``grid`` isn't given.
    dimensions : tuple of Dimension, optional
        Dimensions associated with the object. Only necessary if ``grid`` isn't given.
    dtype : data-type, optional
        Any object that can be interpreted as a numpy data type. Defaults
        to ``np.float32``.
    staggered : Dimension or tuple of Dimension or Stagger, optional
        Define how the Function is staggered.
    padding : int or tuple of ints, optional
        Allocate extra grid points to maximize data access alignment. When a tuple
        of ints, one int per Dimension should be provided.
    initializer : callable or any object exposing the buffer interface, optional
        Data initializer. If a callable is provided, data is allocated lazily.
    allocator : MemoryAllocator, optional
        Controller for memory allocation. To be used, for example, when one wants
        to take advantage of the memory hierarchy in a NUMA architecture. Refer to
        `default_allocator.__doc__` for more information.

    Examples
    --------
    Creation

    >>> from devito import Grid, Function
    >>> grid = Grid(shape=(4, 4))
    >>> f = Function(name='f', grid=grid)
    >>> f
    f(x, y)
    >>> g = Function(name='g', grid=grid, space_order=2)
    >>> g
    g(x, y)

    First-order derivatives through centered finite-difference approximations

    >>> f.dx
    Derivative(f(x, y), x)
    >>> f.dy
    Derivative(f(x, y), y)
    >>> g.dx
    Derivative(g(x, y), x)
    >>> (f + g).dx
    Derivative(f(x, y) + g(x, y), x)

    First-order derivatives through left/right finite-difference approximations

    >>> f.dxl
    Derivative(f(x, y), x)
    >>> g.dxl
    Derivative(g(x, y), x)
    >>> f.dxr
    Derivative(f(x, y), x)

    Second-order derivative through centered finite-difference approximation

    >>> g.dx2
    Derivative(g(x, y), (x, 2))

    Notes
    -----
    The parameters must always be given as keyword arguments, since SymPy
    uses ``*args`` to (re-)create the dimension arguments of the symbolic object.
    """
    def __new__(cls, *args, **kwargs):
        options = kwargs.get('options', {})
        name = kwargs.get('name')
        # Number of dimensions
        ndim = kwargs.get("grid").dim

        # Create the new Function object and invoke __init__
        newobj = sympy.MatrixSymbol.__new__(cls, name, ndim, 1)

        # Initialization. The following attributes must be available
        # when executing __init__
        newobj._name = name
        newobj.__init__(*args, **kwargs)

        # All objects cached on the AbstractFunction /newobj/ keep a reference
        # to /newobj/ through the /function/ field. Thus, all indexified
        # object will point to /newobj/, the "actual Function".
        newobj.function = newobj

        return newobj
            
    def __init__(self, *args, **kwargs):
        # Grid
        self._grid = kwargs.get("grid")
        # Space order
        space_order = kwargs.get('space_order', 1)
        if isinstance(space_order, int):
            self._space_order = space_order
        elif isinstance(space_order, tuple) and len(space_order) == 3:
            self._space_order, _, _ = space_order
        else:
            raise TypeError("`space_order` must be int or 3-tuple of ints")

        # Number of dimensions
        self._ndim = self.grid.dim

        # Name
        self._name = kwargs.get("name")
        
        

    def __getattr__(self, name):
        """
        Try calling a dynamically created FD shortcut.

        .. note::

            This method acts as a fallback for __getattribute__
        """
        try:
            return [c.__getattr__(name) for c in self.components]
        except AttributeError:
            raise AttributeError("%r object has no attribute %r" % (self.__class__, name))

    @components.setter
    def components(self, comp):
        self._components = components

    @property
    def components(self):
        # Initialize components
        components = []
        for d in self.grid.dimensions:
            components += [Function(name=self.name + '_' + d.name,
                                    grid=self.grid, space_order=self.space_order)]
        
        return components

    def _entry(self, i, j, **kwargs):
        return self.components[i]
    
    def __str__(self):
        return sympy.Matrix(self).__str__()

    @property
    def grid(self):
        return self._grid

    @property
    def ndim(self):
        return self._ndim

    @property
    def name(self):
        return self._name

    @property
    def space_order(self):
        return self._space_order

