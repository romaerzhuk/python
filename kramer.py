#!/usr/bin/python
import types
import copy
import re
import polynom

class powers:
  def __init__(self,x):
    #print 'powers.__init__(%s)'%(x)
    s=re.match(r'(\w+)(?:\^(\d+))?',x)
    if s.group(2) is None:
      self.v,self.p=s.group(1),1
    else:
      self.v,self.p=s.group(1),int(s.group(2))
  def copy(self):
    return copy.deepcopy(self)
  def __str__(self):
    if self.p==1:
      return str(self.v)
    else:
      return str(self.v)+'^'+str(self.p)
  def __repr__(self):
    return str(self)
  def __cmp__(self,other):
    if self.v>other.v:
      return 1
    elif self.v<other.v:
      return -1
    else:
      return 0

class multipliers:
  def __init__(self,x):    
    #print 'multipliers.__init__(%s)'%(x)
    sign=x[0]=='-'
    if sign: x=x[1:]  
    s=re.split(r'\*',x)
    #print s
    try:
      self.k,self.l=int(s[0]),s[1:]
    except ValueError:
      self.k,self.l=1,s
    if sign: self.k=-self.k
    for i in xrange(len(self.l)):
      self.l[i]=powers(self.l[i])
    self.normal()
  def normal(self):
    self.l.sort()
    i=0
    while i<len(self.l)-1:
      x,y=self.l[i],self.l[i+1]
      if x==y:
        y.p=x.p+y.p
        del self.l[i]
      else:
        if self.l[i].p==0:
          del self.l[i]
        else:
          i=i+1
  def copy(self):
    return copy.deepcopy(self)
  def __str__(self):
    if self.k==1 and len(self.l)>0:
      f,s=0,''
    elif self.k==-1 and len(self.l)>0:
      f,s=0,'-'
    else:
      f,s=1,str(self.k)
    for i in xrange(len(self.l)):
      if f: s=s+'*'+str(self.l[i])
      else:
        f=1
        s=s+str(self.l[i])
    return s
  def __repr__(self):
    return str(self)
  def __len__(self):
    return len(self.l)
  def __getitem__(self,i):
    return self.l[i]
  def __delitem__(self,i):
    del self.l[i]
  def __eq__(self,x):
    n=len(self.l)
    if n<>len(x.l):
      return 0
    for i in xrange(n):
      if self.l[i]<>x.l[i] or self.l[i].p<>x.l[i].p:
        return 0
    return 1
  def __ne__(self,x): return not self==x
  def __imul__(self,x):
    if type(x) in (types.IntType, types.LongType, types.FloatType):
      self.k=self.k*x
    else:
      self.k=self.k*x.k
      self.l=self.l+copy.deepcopy(x.l)
      self.normal()
    return self
  def __mul__(self,x):
    r=self.copy()
    r.__imul__(x)
    return r
  def __neg__(self):
    r=self.copy()
    r.k=-self.k
    return r

class additors:
  def __init__(self,x):
    #print 'additors.__init__(%s)'%(x)
    self.val=[]
    s=re.split(r'([+-])',x)
    #print s
    sign=0
    i=0
    while i<len(s):
      if s[i]=='+' or s[i]=='-':
        sign=sign^(s[i]=='-')
        del s[i]
      else:
        if len(s[i])>0:
          if sign:
            s[i]='-'+s[i]
          s[i]=multipliers(s[i])
          i=i+1
        else:
          del s[i]
        sign=0
    self.__iadd__(s)
  def copy(self):
    return copy.deepcopy(self)
  def __str__(self):
    l=len(self)
    if l>0:
      s=str(self[0])
      for i in xrange(1,l):
        v=self[i]
        if v.k>=0: s=s+'+'+str(v)
        else:
          v.k=-v.k
          s=s+'-'+str(v)
          v.k=-v.k
      return s
    else: return '0'
  def __repr__(self):
    return str(self)
  def __len__(self): return len(self.val)
  def __getitem__(self,i): return self.val[i]
  def __setitem__(self,i,val): self.val[i]=val
  def __iadd(self,x,f):
    s=self.val
    for i in xrange(len(x)):
      if isinstance(x[i], multipliers):
        m=x[i]
      else:
        m=multipliers(x[i])
      if m.k<>0:        
        try:
          j=s.index(m)
          s[j].k=f(s[j].k,m.k)
          if s[j].k==0: del s[j]
        except ValueError:
          s.append(m.copy())
    return self
  def __iadd__(self,x):
    self.__iadd(x,lambda x,y:x+y)
    return self
  def __add__(self,x):
    r=self.copy()
    r.__iadd__(x)
    return r
  def __neg__(self):
    r=self.copy()
    for i in xrange(len(r)):
      r[i]=-r[i]
    return r
  def __isub__(self,x):
    self.__iadd(x,lambda x,y:x-y)
    return self
  def __sub__(self,x):
    r=self.copy()
    r.__isub__(x)
    return r
  def __imul__(self,x):
    if isinstance(x, additors) or type(x) is types.ListType:
      v=self.val
      self.val=[]
      l=self.copy()
      l.val=v
      for i in xrange(len(x)):
        self.__iadd__(l*x[i])
    else:
      for i in xrange(len(self)):
        self[i].__imul__(x)
    return self
  def __mul__(self,x):
    r=self.copy()
    r.__imul__(x)
    return r
  def factor(self,x):
    lst=[]
    for i in xrange(len(self)):
      m=self.val[i].copy()
      count=0
      for j in xrange(len(m)):
        if m[j].v==x:
          count=m[j].p
          del m[j]
          break
      dif=count-len(lst)+1
      if dif>0: lst.extend([None]*dif)
      if lst[count] is None:
        lst[count]=additors('0')
      lst[count]=lst[count]+m
    s=''
    for i in xrange(len(lst)):
      if lst[i] is None: continue
      p='('+str(lst[i])+')'
      if i:
        p=p+'*'+x
        if i>1: p=p+str(i)
      if s is '': s=p
      else:       s=p+s
    return s

class matrix:
  def __init__(self,x):
    self.val=[]
    for i in xrange(len(x)):
      v=x[i]
      self.val.append([])
      s=self.val[i]
      for j in xrange(len(v)):
        s.append(copy.deepcopy(v[j]))
  def copy(self):
    return copy.deepcopy(self)
  def create(self):
    val=self.val
    self.val=None
    r=self.copy()
    self.val=val
    return r
  def __str__(self):
    v=self.val
    s=''
    for i in xrange(len(v)):
      x=v[i]
      z=''
      s=s+'\n'
      for j in xrange(len(x)):
        s=s+z+'\t'+str(v[i][j])
        z=','
    return s
  def __len__(self):
    return len(self.val)
  def det(self):
    l=len(self.val)
    #print 'begin det %dx%d\n'%(l,l),self
    if l<2:
      if l<1:
        sum=None
      else:
        sum=self.val[0][0]
    else:
      sign=1
      r=self.create()
      r.val=[None]*(l-1)
      for i in xrange(l):
        k=0
        for j in xrange(l):
          if i<>j:
            r.val[k]=self.val[j][1:l]
            #print 'slice=',self.val[j][1:l]
            k=k+1
        if i==0:
          sum=self.val[i][0]*r.det()
        else:
          if sign: sum=sum-self.val[i][0]*r.det()
          else:    sum=sum+self.val[i][0]*r.det()
          sign=not sign
    #print 'end det',sum
    return sum
  def kramer(self,num=None):
    """ Solution of linear equations by Kramer's method.
        matrix[m x n], m=n+1
        num - number of variable (0..n)
        if num = None, decided all variable
    """
    n=len(self.val)-1
    if num is None:
      num=range(n)
    l=len(num)
    x=[None]*l
    m=self.create()
    m.val=self.val[:l]
    d=m.det()
    for k in xrange(l):
      i=num[k]
      m.val[i]=self.val[l]
      x[i]=m.det()
      m.val[i]=self.val[i]
    return d,x
        
def test():
  p=powers('x12we^34')
  q=powers('x123s')
  print '%s, %s'%(p,q)
  m=multipliers('3*x^2*a1')
  p=m*m
  print 'm=',m,'m*m=',p
  a=additors('3*x^2*a1+3*x^2*a1+2*x*y-7*a1*x')
  print 'a=%s, a.factor(x)=%s'%(a,a.factor('x'))
  return
  b=-additors('3*x^2*a1')
  print 'b=',b
  print 'a+b=',a+b
  print 'a-b=',a-b
  print 'a*b=',a*b
  p=polynom.polynom([b,a,b])
  print 'p=',p
  q=polynom.polynom([a,a,b])
  print 'q=',q
  print 'p+q=',p+q
  a=additors('a+2*b')
  b=additors('3*x-y')
  c=additors('-x')
  p=polynom.polynom([a,b])
  print 'p=',p
  q=polynom.polynom([b,c])
  print 'q=',q
  print 'p*q=',p*q
  m=matrix([[1,2,3],[4,0,6],[7,8,9]])
  print 'm=',m
  print 'm.det()=',m.det()
  m.val.append([1,0,0])
  print 'm.kramer()=',m.kramer()
  print 'OK'

if __name__=='__main__':
  test()
