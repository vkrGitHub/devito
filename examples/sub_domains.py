import numpy as np

from devito import Grid, Dimension
from devito import SubDomain, SubDimension
from devito.types import SubDomains

from devito import Function, TimeFunction, Eq, Constant, Operator, solve

from sympy.utilities.lambdify import lambdify, implemented_function
from sympy.abc import z

from math import floor

n_domains = 10
extent = np.zeros((n_domains,2,2), dtype=int)

for j in range(0,extent.shape[0]):
    extent[j,0,0] = j                          # xmin
    extent[j,0,1] = j                          # xmax
    extent[j,1,0] = j-floor(j/2)               # ymin
    extent[j,1,1] = n_domains-1-j-floor(j/2)   # ymax

class MyDomains(SubDomains):
    name = 'MyDomains'
    def define(self, dimensions):
        x, y = dimensions
        #xmn = implemented_function('xmn', lambda z: extent[z,0,0])
        #xmx = implemented_function('xmx', lambda z: extent[z,0,1])
        #ymn = implemented_function('ymn', lambda z: extent[z,1,0])
        #ymx = implemented_function('ymx', lambda z: extent[z,1,1])
        #lxmn = lambdify(self.indices, xmn(self.indices))
        #lxmx = lambdify(self.indices, xmx(self.indices))
        #lymn = lambdify(self.indices, ymn(self.indices))
        #lymx = lambdify(self.indices, ymx(self.indices))
        #return {x: ('middle', self.extent[n,0,0], n_domains-1-self.extent[n,0,1]),
                #y: ('middle', self.extent[n,1,0], n_domains-1-self.extent[n,1,1])}
        return {x: ('middle', self.extent[0,0,0], n_domains-1-self.extent[0,0,1]),
                y: ('middle', self.extent[0,1,0], n_domains-1-self.extent[0,1,1])}
    
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
op = Operator(eq)
op.apply()

print(op.ccode)

from IPython import embed
embed()