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

#f = TimeFunction(name='f', grid=grid)
#f.data[:] = 0.0
#eq = Eq(f.dt, 1, subdomain = grid.subdomains['MyDomains'])
#stencil = solve(eq, f.forward)
#op = Operator(Eq(f.forward, stencil))
#op.apply(time_m=0, time_M=2, dt=1)

f = Function(name='f', grid=grid)
f.data[:] = 0.0
eq = Eq(f, 1, subdomain = grid.subdomains['MyDomains'])

#eq_xl = Eq(xm, extent[0,0,0])
#eq_xr = Eq(xM, extent[0,0,1])
#eq_yl = Eq(ym, extent[0,1,0])
#eq_yr = Eq(yM, extent[0,1,1])
#eq_xl = Eq(xm, subs.indices)
#eq_xr = Eq(xM, subs.indices)
eq_yl = Eq(ym, 1)
#eq_yr = Eq(yM, 1)

#op = Operator([eq_yl, eq_yr])
#op = Operator([eq, eq_xl, eq_xr, eq_yl, eq_yr])
op = Operator(eq)

#op = Operator(eq_yl)

#op.apply()

print(op.ccode)

from IPython import embed
embed()