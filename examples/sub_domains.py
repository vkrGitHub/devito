import numpy as np

from devito import Grid
from devito import SubDomain, SubDimension
from devito.types import SubDomains

from devito import TimeFunction, Eq, Constant, Operator

from math import floor

n_domains = 10
extent = np.zeros((n_domains,2,2))

for j in range(0,extent.shape[0]):
    extent[j,0,0] = j
    extent[j,0,1] = j
    extent[j,1,0] = j-floor(j/2) 
    extent[j,1,1] = n_domains-1-floor(j/2)

class MyDomains(SubDomains):
    name = 'MyDomains'
    def define(self, dimensions):
        x, y = dimensions
        xm = Constant(name='xm')
        xM = Constant(name='xM')
        ym = Constant(name='ym')
        yM = Constant(name='yM')
        xi = SubDimension.middle('xi', x, xm, xM)
        yi = SubDimension.middle('yi', y, ym, yM)
        return {x: ('middle', xi.symbolic_min, xi.symbolic_max),
                y: ('middle', yi.symbolic_min, yi.symbolic_max)}
    
subs = MyDomains(n_domains=n_domains, extent=extent)
    
grid = Grid(extent=(10, 10), shape=(10, 10), origin=(0, 0), subdomains = (subs))

f = TimeFunction(name='f', grid=grid)

x, y = grid.dimensions

eq = Eq(f, x, subdomain = grid.subdomains['MyDomains'])

op = Operator(eq)
    
#from IPython import embed
#embed()
print(op.ccode)
