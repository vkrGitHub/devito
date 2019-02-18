from devito import Grid
from devito import SubDomain

from devito import Function, Eq

n_domains = 10

class SubyD(SubDomain):
    name = 'SubyD'
    def define(self, dimensions):
        x, y = dimensions
        xi = SubDimension.middle('xi', x, 1, 1)
        yi = SubDimension.middle('xi', x, 1, 1)
        return {x: ('middle', x0, x1), y: ('middle', y0, y1)}
    
sd = SubyD()
    
grid = Grid(extent=(10, 10), shape=(10, 10), origin=(0, 0), subdomains = sd)

f = Function(name='f', grid=grid)

x, y = grid.dimensions

Eq(f, x, subdomain = grid.subdomains['SubyD'])
    
#from IPython import embed
#embed()