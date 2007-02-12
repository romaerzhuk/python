from clean import clean
from os import system, listdir, remove
from dir import through_dirs
import re
import sys

class Remover:
  def __init__(self,num):
    self.num=num
  def __call__(self,path):
    r=re.compile(r'\d\d\d\d-\d\d-\d\d')
    list=filter(lambda i: r.search(i)!=None, listdir(path))
    list.sort(lambda x, y: ((r.search(y).group(0)>=r.search(x).group(0))<<1)-1)
    for i in list[self.num:]:
      remove(path+'/'+i)

def arch(list):
  arhiv='arhiv'
  #print list
  for i in list:
    #print i
    name,num,files=i.split('$')
    #print "name=",name,"num=",num,"files=",files
    #if files[0]==':': continue
    num=int(num)
    rar='rar a -r -m5 -agYYYY.MM.DD '+arhiv+'/'+name+'/'+name+' '+files
    system(rar)
    del_old=Remover(num)
    through_dirs(arhiv+'/'+name, del_old)
  del_old=Remover(3)
  through_dirs(arhiv, del_old)

if __name__=='__main__':
  arch(sys.argv[1:])
