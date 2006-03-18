#!/usr/bin/python
from kramer import additors, matrix
#from polynom import polynom

m=[['z-1',   '0',     '0',   '-q1'], \
   ['a12*z', 'a*z-1', 'w1',  '0'],   \
   ['b1*z',  'b2*z',  '-w1', 'q0'],  \
   ['0',     '0',     '1',   '-q2'], \
   ['0',     '0',     '1',   'q3']]
for i in xrange(len(m)):
  for j in xrange(len(m[i])):
    m[i][j]=additors(m[i][j])
m=matrix(m)
print 'm=',m
det,lst=m.kramer()
print '( %s ) * Ksi = ( %s ) * Fi'%(lst[3],det)
print 'OK'