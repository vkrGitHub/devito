import numpy as np

from devito import Grid, Dimension
from devito import dimensions, SubDomain, SubDimension
from devito.types import SubDomains

from devito import Function, TimeFunction, Eq, Constant, Operator, solve

from sympy.utilities.lambdify import lambdify, implemented_function
from sympy.abc import z

from math import floor

n_domains = 10
extent = np.zeros((n_domains,2,2), dtype=int)

dummy_const = Constant(name='dummy_const', dtype=int)
dummy_const = 0

for j in range(0,extent.shape[0]):
    extent[j,0,0] = j
    extent[j,0,1] = n_domains-1-j
    extent[j,1,0] = floor(j/2)
    extent[j,1,1] = floor(j/2)

class MyDomains(SubDomains):
    name = 'MyDomains'
    def define(self, dimensions):
        x, y = dimensions
        return {x: ('middle', 0, 0),
                y: ('middle', 0, 0)}

subs = MyDomains(n_domains=n_domains, extent=extent)

grid = Grid(extent=(10, 10), shape=(10, 10), origin=(0, 0), subdomains = (subs))
x, y = grid.dimensions

f = TimeFunction(name='f', grid=grid)
f.data[:] = 0.0
eq = Eq(f.dt, 1, subdomain = grid.subdomains['MyDomains'])

n = subs.indices

bounds_xm = Function(name='bounds_xm', dimensions = (n, ), shape = (n_domains, ))
bounds_xM = Function(name='bounds_xM', dimensions = (n, ), shape = (n_domains, ))
bounds_ym = Function(name='bounds_ym', dimensions = (n, ), shape = (n_domains, ))
bounds_yM = Function(name='bounds_yM', dimensions = (n, ), shape = (n_domains, ))

bounds_xm.data[:] = extent[:,0,0]
bounds_xM.data[:] = extent[:,0,1]
bounds_ym.data[:] = extent[:,1,0]
bounds_yM.data[:] = extent[:,1,1]

dummy_func = Function(name='dummy_func', dimensions = (n, ), shape = (n_domains, ))

eq_xm = Eq(subs.dimensions[0]._symbolic_thickness('xi')[0], bounds_xm[n])
eq_xM = Eq(subs.dimensions[0]._symbolic_thickness('xi')[1], bounds_xM[n])
eq_ym = Eq(subs.dimensions[1]._symbolic_thickness('yi')[0], bounds_ym[n])
eq_yM = Eq(subs.dimensions[1]._symbolic_thickness('yi')[1], bounds_yM[n])

dummy_eq = Eq(dummy_func[n], dummy_const)

stencil = Eq(f.forward, solve(eq, f.forward))

op = Operator([eq_xm, eq_xM, eq_ym, eq_yM, dummy_eq, stencil])
print(op.ccode)

op.apply(t_m=0, t_M=3, dt=1)

print(f.data[-1,:,:].transpose())

from IPython import embed; embed()