#!/usr/bin/python
import types
import copy

class array:
  def __init__(self,x):
    if type(x) is types.IntType:
      assert x>0
      self.val=[None]*x
    else:
      s=len(x)
      self.val=[None]*s
      for i in xrange(s):
        self[i]=copy.deepcopy(x[i])
  def copy(self):
    return copy.deepcopy(self)
  def __str__(self):
    return str(self.val)
  def __len__(self):
    return len(self.val)
  def __getitem__(self,i):
    return self.val[i]
  def __setitem__(self,i,val):
    if type(val) is types.IntType or type(val) is types.LongType:
      self.val[i]=float(val)
    else:
      self.val[i]=val
  def foreachpair(self,other,f1,f2):
    n=len(self)
    m=len(other)
    l=min(n,m)
    for i in xrange(l):
      self[i]=f1(self[i],other[i])
    if n<m:
      for i in xrange(l,m):
        self.val.append(f2(other[i]))
    return self
  def __iadd__(self,other):
    return self.foreachpair(other,lambda x,y:x+y,lambda x:copy.deepcopy(x))
  def __add__(self,other):
    r=self.copy()
    r.__iadd__(other)
    return r
  def __isub__(self,other):
    return self.foreachpair(other,lambda x,y:x-y,lambda x:-x)
  def __sub__(self,other):
    r=self.copy()
    r.__isub__(other)
    return r

class polynom(array):
  def __init__(self,other):
    array.__init__(self,other)
  #def __str__(self):
  #  return str()
  #  l=len(self)
  #  if l>0:
  #    s=str(self[0])
  #    if l>1:
  #      s=str(self[1])+'*z + '+s
  #    for i in xrange(2,l):
  #      s=str(self[i])+'*z^'+str(i)+' + '+s
  #    return s
  #  else: return '0'
  #  return str(self.val)
  def __mul__(self,other):
    if isinstance(other,polynom):
      l=len(self)
      s=len(other)
      r=polynom(l+s-1)
      for i in xrange(s):
        p=self*other[i]
        if i==0:
          r.val[:l]=p.val
        else:
          for j in xrange(l-1):
            r[i+j]=r[i+j]+p[j]
          r[i+l-1]=p[l-1]
    else:
      l=len(self)
      r=polynom(l)
      for i in xrange(l):
        r[i]=self[i]*other
    return r

class point_polynom:
  def __init__(self,p):
    self.x0,self.lst=p[0],polynom(p[1])
  def copy(self):
    return copy.deepcopy(self)
  def __str__(self):
    return '('+str(self.x0)+', '+str(self.lst)+')'
  def __iadd__(self,other):
    assert self.x0==other.x0
    self.lst.__iadd__(other.lst)
    return self
  def __add__(self,other):
    r=self.copy()
    r.__iadd__(other)
    return r
  def __isub__(self,other):
    assert self.x0==other.x0
    self.lst.__isub__(other.lst)
    return self
  def __sub__(self,other):
    r=self.copy()
    r.__isub__(other)
    return r
  def __imul__(self,other):
    assert self.x0==other.x0
    self.lst=self.lst*other.lst
    return self
  def __mul__(self,other):
    r=self.copy()
    r.__imul__(other)
    return r
  def __call__(self,x):
    x=x-self.x0
    m=x
    p=self.lst
    y=p[0]
    for i in xrange(1,len(p)):
      y=y+p[i]*m
      m=m*x
    return y
  def integral(self,x0,y0):
    r=self.copy()
    q=r.lst
    q.val.insert(0,0)
    for i in xrange(2,len(q)):
      q[i]=q[i]/i
    q[0]=y0-r(x0)
    return r

class function:
  def __init__(self,f):
    if type(f) is types.IntType:
      assert f>0
      self.val=[None]*f
    else:
      s=len(f)
      self.val=[None]*s
      q=self.val
      for i in xrange(s):
        q[i]=point_polynom(f[i])
  def __len__(self):
    return len(self.val)
  def __getitem__(self,i):
    return self.val[i]
  def __str__(self):
    l=len(self)
    s='['
    if l>0:
      s=s+str(self[0])
      for i in xrange(1,len(self)):
        s=s+',\\\n'+str(self[i])
      return s+']'
  def foreachpair(self,other,func):
    s=len(self)
    r=function(s)
    assert s==len(other)
    for i in xrange(s):
      r[i]=func(self[i],other[i])
    return r
  def __add__(self,other):
    return self.foreachpair(other,lambda x,y: x+y)
  def __radd__(self,other):
    return self+other
  def __sub__(self,other):
    return self.foreachpair(other,lambda x,y: x-y)
  def __call__(self,x):
    i1=0
    i2=len(self)-1
    while i2<>i1:
      i=(i2+i1)/2
      if self[i].x0<x:
        i1=i+1
      else:
        i2=i
    return self[i1](x)
  def integral(self,x0,y0):
    s=len(self)
    r=function(s)
    for i in xrange(s):
      r.val[i]=self[i].integral(x0,y0)
      q=r[i]
      x0=q.x0
      y0=q.lst[0]
    return r

def test():
  a=array(2)
  print 'a=',a
  a=array([2,3])
  print 'a=',a
  print 'a+a=',a+a
  p=polynom(3)
  print 'p=',p
  p=polynom([-1,3.5])
  print 'p=',p
  q=polynom([2.5,1])
  print 'q=',q
  print 'p+q=',p+q
  print 'p-q=',p-q
  print 'p*q=',p*q
  q=point_polynom((1.5, 5))
  print 'q=',q
  p=point_polynom((1, [3,-4.5]))
  print 'p=',p
  q=point_polynom((1, [5,2.5,1]))
  print 'q=',q
  print 'p+q=',p+q
  print 'p-q=',p-q
  print 'p*q=',p*q
  print "p(1)=",p(1),", p(0)=",p(0)
  print "p.integral(0,-1)=",p.integral(0,-1)
  f=function([(0, [0]),(0.25, [1]), (0.75, [-1]), (1, [1]), (5, [0])])
  print "f=",f
  print "f(0.5)=",f(0.5)
  print "f.integral(0,0)=",f.integral(0,0)
  print 'OK' 

if __name__=='__main__':
  test()
