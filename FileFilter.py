# -*- coding: cp1251 -*-
import re, types, ListFile

class Filter:
  """
  Из списка масок файлов формирует регулярное выражение
  """
  def __init__(self, list):
    if type(list) is types.StringType:
      list = ListFile.List(list)
    extlist,vl = '',''
    for line in list:
      line="("+line.replace("\\", "/").replace(".", "\\.").replace("*",".*")+"$)"
      extlist += vl + line
      vl = '|'
    self.re=re.compile(extlist, re.IGNORECASE)
  
  def __call__(self, name):
    return len(name)>0 and self.re.search(name)!=None


def test():
  ffilter=Filter(['*.cpp', 'dir\\abs*log'])
  lst=['xyz.cpp', 'xdcpp', 'dir/abssb.log', 'x.cpp2']
  assert(ffilter(lst[0]))
  assert(not ffilter(lst[1]))
  assert(ffilter(lst[2]))
  assert(not ffilter(lst[3]))

if __name__=='__main__':
  test()
