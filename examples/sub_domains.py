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

xm = Constant(name='xm', dtype=int)
xM = Constant(name='xM', dtype=int)
ym = Constant(name='ym', dtype=int)
yM = Constant(name='yM', dtype=int)

dummy_const = Constant(name='dummy_const', dtype=int)

for j in range(0,extent.shape[0]):
    extent[j,0,0] = j                          # xmin
    extent[j,0,1] = j                          # xmax
    extent[j,1,0] = j-floor(j/2)               # ymin
    extent[j,1,1] = n_domains-1-j-floor(j/2)   # ymax

class MyDomains(SubDomains):
    name = 'MyDomains'
    def define(self, dimensions):
        x, y = dimensions
        return {x: ('middle', xm, xM),
                y: ('middle', ym, yM)}
    
subs = MyDomains(n_domains=n_domains, extent=extent)
    
grid = Grid(extent=(10, 10), shape=(10, 10), origin=(0, 0), subdomains = (subs))
x, y = grid.dimensions

f = Function(name='f', grid=grid)
f.data[:] = 0.0
eq = Eq(f, 1, subdomain = grid.subdomains['MyDomains'])

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

eq_xm = Eq(xm, bounds_xm[n])
eq_xM = Eq(xM, bounds_xM[n])
eq_ym = Eq(ym, bounds_ym[n])
eq_yM = Eq(yM, bounds_yM[n])
dummy_eq = Eq(dummy_func[n], dummy_const)

op = Operator([eq_xm, eq_xM, eq_ym, eq_yM, eq])
print(op.ccode)

#op.apply()

from IPython import embed; embed()