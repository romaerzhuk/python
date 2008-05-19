#!/usr/bin/python
from polynom import *

scale=1
ampl=1
k=ampl/(0.25*scale*scale)
delta=function([(0, [0]), (0.5*scale, [-k]), \
 (1*scale, [k]), (5*scale, [0])])
delta=delta.integral(0,0).integral(0,0)
v=function([(0, [0]), (5*scale, [1])])

#delta2=delta
#fi=v
#teta=delta2.integral(0,0)
#v=fi.integral(0,0)

#delta=teta.integral(0,0)
#v=v.integral(0,0)
#print "t fi delta2 ksi"
print "t v delta x"
n=301
for i in xrange(n):
  x=i*1.5*scale/(n-1)
  #print x,fi(x),delta2(x),delta2(x)+fi(x)
  print x,v(x),delta(x),delta(x)+v(x)
