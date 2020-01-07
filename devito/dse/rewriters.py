import abc
from collections import OrderedDict
from time import time

from sympy import cos, sin

from devito.ir import (DataSpace, IterationSpace, Interval, IntervalGroup,
                       detect_accesses, build_intervals)
from devito.dse.aliases import collect
from devito.dse.manipulation import (collect_nested, common_subexprs_elimination,
                                     make_is_time_invariant)
from devito.exceptions import DSEException
from devito.logger import dse_warning as warning
from devito.symbolics import (bhaskara_cos, bhaskara_sin, estimate_cost, freeze,
                              pow_to_mul, q_leaf, q_sum_of_product, q_terminalop,
                              yreplace)
from devito.tools import flatten
from devito.types import Array, Eq, Scalar

__all__ = ['BasicRewriter', 'AdvancedRewriter', 'AggressiveRewriter', 'CustomRewriter']


class State(object):

    def __init__(self, cluster, template):
        self.clusters = [cluster]
        self.template = template
        # Track performance of each pass
        self.ops = OrderedDict()
        self.timings = OrderedDict()

    def update(self, clusters):
        self.clusters = clusters or self.clusters


def dse_pass(func):

    def wrapper(self, state, **kwargs):
        # Invoke the DSE pass on each Cluster
        tic = time()
        state.update(flatten([func(self, c, state.template, **kwargs)
                              for c in state.clusters]))
        toc = time()

        # Profiling
        key = '%s%d' % (func.__name__, len(state.timings))
        state.timings[key] = toc - tic
        if self.profile:
            candidates = [c.exprs for c in state.clusters if c.is_dense]
            state.ops[key] = estimate_cost(flatten(candidates))

    return wrapper


class AbstractRewriter(object):

    """
    Transform a Cluster of SymPy expressions into one or more clusters with
    reduced operation count.
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, profile=True, template=None):
        self.profile = profile

        assert callable(template)
        self.template = template

    def run(self, cluster):
        state = State(cluster, self.template)

        self._pipeline(state)

        self._finalize(state)

        return state

    @abc.abstractmethod
    def _pipeline(self, state):
        return

    @dse_pass
    def _finalize(self, cluster, *args, **kwargs):
        """
        Finalize the DSE output: ::

            * Pow-->Mul. Convert integer powers in an expression to Muls,
              like a**2 => a*a.
            * Freezing. Make sure that subsequent SymPy operations applied to
              the expressions in ``cluster.exprs`` will not alter the effect of
              the DSE passes.
        """
        exprs = [pow_to_mul(e) for e in cluster.exprs]
        return cluster.rebuild([freeze(e) for e in exprs])


class BasicRewriter(AbstractRewriter):

    def _pipeline(self, state):
        self._extract_increments(state)

    @dse_pass
    def _extract_increments(self, cluster, template, **kwargs):
        """
        Extract the RHS of non-local tensor expressions performing an associative
        and commutative increment, and assign them to temporaries.
        """
        processed = []
        for e in cluster.exprs:
            if e.is_Increment and e.lhs.function.is_Input:
                handle = Scalar(name=template(), dtype=e.dtype).indexify()
                if e.rhs.is_Number or e.rhs.is_Symbol:
                    extracted = e.rhs
                else:
                    extracted = e.rhs.func(*[i for i in e.rhs.args if i != e.lhs])
                processed.extend([e.func(handle, extracted, is_Increment=False),
                                  e.func(e.lhs, handle)])
            else:
                processed.append(e)

        return cluster.rebuild(processed)

    @dse_pass
    def _eliminate_intra_stencil_redundancies(self, cluster, template, **kwargs):
        """
        Perform common subexpression elimination, bypassing the tensor expressions
        extracted in previous passes.
        """
        make = lambda: Scalar(name=template(), dtype=cluster.dtype).indexify()
        processed = common_subexprs_elimination(cluster.exprs, make)

        return cluster.rebuild(processed)

    @dse_pass
    def _optimize_trigonometry(self, cluster, **kwargs):
        """
        Rebuild ``exprs`` replacing trigonometric functions with Bhaskara
        polynomials.
        """
        processed = []
        for expr in cluster.exprs:
            handle = expr.replace(sin, bhaskara_sin)
            handle = handle.replace(cos, bhaskara_cos)
            processed.append(handle)

        return cluster.rebuild(processed)


class AdvancedRewriter(BasicRewriter):

    MIN_COST_ALIAS = 10
    """
    Minimum operation count of an alias (i.e., "redundant") expression
    to be lifted into a vector temporary.
    """

    MIN_COST_ALIAS_INV = 50
    """
    Minimum operation count of a time-invariant alias (i.e., "redundant")
    expression to be lifted into a vector temporary. Time-invariant aliases
    are lifted outside of the time-marching loop, thus they will require
    vector temporaries as big as the entire grid.
    """

    MIN_COST_FACTORIZE = 100
    """
    Minimum operation count of an expression so that aggressive factorization
    is applied.
    """

    def _pipeline(self, state):
        self._extract_time_invariants(state)
        self._eliminate_inter_stencil_redundancies(state)
        self._eliminate_intra_stencil_redundancies(state)
        self._factorize(state)

    @dse_pass
    def _extract_time_invariants(self, cluster, template, **kwargs):
        """
        Extract time-invariant subexpressions, and assign them to temporaries.
        """
        make = lambda: Scalar(name=template(), dtype=cluster.dtype).indexify()
        rule = make_is_time_invariant(cluster.exprs)
        costmodel = lambda e: estimate_cost(e, True) >= self.MIN_COST_ALIAS_INV
        processed, found = yreplace(cluster.exprs, make, rule, costmodel, eager=True)

        return cluster.rebuild(processed)

    @dse_pass
    def _factorize(self, cluster, *args, **kwargs):
        """
        Factorize trascendental functions, symbolic powers, numeric coefficients.

        If the expression has an operation count greater than
        ``self.MIN_COST_FACTORIZE``, then the algorithm is applied recursively
        until no more factorization opportunities are detected.
        """
        processed = []
        for expr in cluster.exprs:
            handle = collect_nested(expr)
            cost_handle = estimate_cost(handle)

            if cost_handle >= self.MIN_COST_FACTORIZE:
                handle_prev = handle
                cost_prev = estimate_cost(expr)
                while cost_handle < cost_prev:
                    handle_prev, handle = handle, collect_nested(handle)
                    cost_prev, cost_handle = cost_handle, estimate_cost(handle)
                cost_handle, handle = cost_prev, handle_prev

            processed.append(handle)

        return cluster.rebuild(processed)

    @dse_pass
    def _eliminate_inter_stencil_redundancies(self, cluster, template, **kwargs):
        """
        Search aliasing expressions and capture them into vector temporaries.

        Examples
        --------
        1) temp = (a[x,y,z]+b[x,y,z])*c[t,x,y,z]
           >>>
           ti[x,y,z] = a[x,y,z] + b[x,y,z]
           temp = ti[x,y,z]*c[t,x,y,z]

        2) temp1 = 2.0*a[x,y,z]*b[x,y,z]
           temp2 = 3.0*a[x,y,z+1]*b[x,y,z+1]
           >>>
           ti[x,y,z] = a[x,y,z]*b[x,y,z]
           temp1 = 2.0*ti[x,y,z]
           temp2 = 3.0*ti[x,y,z+1]
        """
        exprs = cluster.exprs

        # For more information about "aliases", refer to collect.__doc__
        aliases = collect(exprs)

        # Redundancies will be stored in space-varying temporaries
        is_time_invariant = make_is_time_invariant(exprs)
        time_invariants = {e.rhs: is_time_invariant(e) for e in exprs}

        # Find the candidate expressions
        processed = []
        candidates = OrderedDict()
        for e in exprs:
            # Cost check (to keep the memory footprint under control)
            naliases = len(aliases.get(e.rhs))
            cost = estimate_cost(e, True)*naliases
            test0 = lambda: cost >= self.MIN_COST_ALIAS and naliases > 1
            test1 = lambda: cost >= self.MIN_COST_ALIAS_INV and time_invariants[e.rhs]
            if test0() or test1():
                candidates[e.rhs] = e.lhs
            else:
                processed.append(e)

        # Create alias Clusters and all necessary substitution rules
        # for the new temporaries
        alias_clusters = []
        subs = {}
        for origin, alias in aliases.items():
            if all(i not in candidates for i in alias.aliased):
                continue

            # The write-to Intervals
            writeto = [Interval(i.dim, *alias.relaxed_diameter.get(i.dim, (0, 0)))
                       for i in cluster.ispace.intervals if not i.dim.is_Time]
            writeto = IntervalGroup(writeto)

            # Optimization: no need to retain a SpaceDimension if it does not
            # induce a flow/anti dependence (below, `i.offsets` captures this, by
            # telling how much halo will be needed to honour such dependences)
            dep_inducing = [i for i in writeto if any(i.offsets)]
            try:
                index = writeto.index(dep_inducing[0])
                writeto = IntervalGroup(writeto[index:])
            except IndexError:
                warning("Couldn't optimize some of the detected redundancies")

            # Create a temporary to store `alias`
            dimensions = [d.root for d in writeto.dimensions]
            halo = [(abs(i.lower), abs(i.upper)) for i in writeto]
            array = Array(name=template(), dimensions=dimensions, halo=halo,
                          dtype=cluster.dtype)

            # Build up the expression evaluating `alias`
            access = tuple(i.dim - i.lower for i in writeto)
            expression = Eq(array[access], origin.xreplace(subs))

            # Create the substitution rules so that we can use the newly created
            # temporary in place of the aliasing expressions
            for aliased, distance in alias.with_distance:
                assert all(i.dim in distance.labels for i in writeto)
                access = [i.dim - i.lower + distance[i.dim] for i in writeto]
                if aliased in candidates:
                    # It would *not* be in `candidates` if part of a composite alias
                    subs[candidates[aliased]] = array[access]
                subs[aliased] = array[access]

            # Construct the `alias` IterationSpace
            intervals, sub_iterators, directions = cluster.ispace.args
            ispace = IterationSpace(intervals.add(writeto), sub_iterators, directions)

            # Construct the `alias` DataSpace
            mapper = detect_accesses(expression)
            parts = {k: IntervalGroup(build_intervals(v)).add(ispace.intervals)
                     for k, v in mapper.items() if k}
            dspace = DataSpace(cluster.dspace.intervals, parts)

            # Create a new Cluster for `alias`
            alias_clusters.append(cluster.rebuild(exprs=[expression],
                                                  ispace=ispace, dspace=dspace))

        # Switch temporaries in the expression trees
        processed = [e.xreplace(subs) for e in processed]

        return alias_clusters + [cluster.rebuild(processed)]


class AggressiveRewriter(AdvancedRewriter):

    def _pipeline(self, state):
        self._extract_sum_of_products(state)
        self._extract_time_invariants(state)
        self._eliminate_inter_stencil_redundancies(state)

        self._extract_sum_of_products(state)
        self._eliminate_inter_stencil_redundancies(state)
        self._extract_sum_of_products(state)

        self._factorize(state)
        self._eliminate_intra_stencil_redundancies(state)

    @dse_pass
    def _extract_sum_of_products(self, cluster, template, **kwargs):
        """
        Extract sub-expressions in sum-of-product form, and assign them to temporaries.
        """
        make = lambda: Scalar(name=template(), dtype=cluster.dtype).indexify()
        rule = q_sum_of_product
        costmodel = lambda e: not (q_leaf(e) or q_terminalop(e))
        processed, _ = yreplace(cluster.exprs, make, rule, costmodel)

        return cluster.rebuild(processed)


class CustomRewriter(AggressiveRewriter):

    passes_mapper = {
        'extract_sop': AggressiveRewriter._extract_sum_of_products,
        'factorize': AggressiveRewriter._factorize,
        'gcse': AggressiveRewriter._eliminate_inter_stencil_redundancies,
        'cse': AggressiveRewriter._eliminate_intra_stencil_redundancies,
        'extract_invariants': AdvancedRewriter._extract_time_invariants,
        'extract_increments': BasicRewriter._extract_increments,
        'opt_transcedentals': BasicRewriter._optimize_trigonometry
    }

    def __init__(self, passes, template=None, profile=True):
        try:
            passes = passes.split(',')
        except AttributeError:
            # Already in tuple format
            if not all(i in CustomRewriter.passes_mapper for i in passes):
                raise DSEException("Unknown passes `%s`" % str(passes))
        self.passes = passes
        super(CustomRewriter, self).__init__(profile, template)

    def _pipeline(self, state):
        for i in self.passes:
            CustomRewriter.passes_mapper[i](self, state)
