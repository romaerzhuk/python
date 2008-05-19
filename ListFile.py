# -*- coding: cp1251 -*-
"""
������ ���������� ����� � ���������� ��� � ������
"""
class List:
   def __init__(self,file):
     self.file=file
   def __iter__(self):
     return ListIter(self.file)

"""
�������� �����
"""
class ListIter:
  def __init__(self,filename):
    self.file=file(filename)
  def __iter__(self):
    return self
  def next(self):
    line=self.file.readline()
    if len(line)<=0:
        raise StopIteration
    return line.replace('\n','')

def test():
  for i in List('ListFile.py'):
    assert(i=='"""')
    break

if __name__=='__main__':
  test()
