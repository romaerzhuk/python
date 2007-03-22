from clean import clean
from os import system, listdir, remove
from dir import through_dirs
import re
import sys
import time

class Remover:
  def __init__(self,num):
    self.num=num
  def __call__(self,path):
    r=re.compile(r'\d\d\d\d-\d\d-\d\d')
    list=filter(lambda i: r.search(i)!=None, listdir(path))
    list.sort(lambda x, y: ((r.search(y).group(0)>=r.search(x).group(0))<<1)-1)
    for i in list[self.num:]:
      remove(path+'/'+i)

def backup(dir,command,list):
  #print dir,command,list
  del_old=Remover(3)
  through_dirs(dir, del_old)
  for i in list:
    name,files,num=i.split('$')
    #print "name='%1s'\nfiles='%2s'\nnum='%3s'" % (name,files,num)
    #if files[0]==':': continue
    num=int(num)
    print command % (dir+'/'+name+'/'+name+time.strftime("%Y-%m-%d"), files)
    system(command % (dir+'/'+name+'/'+name+time.strftime("%Y-%m-%d"), files))
    through_dirs(dir+'/'+name, Remover(num))
  through_dirs(dir, del_old)

if __name__=='__main__':
  # use: backup.py dir-name command list
  # command example: 'tar xvzf %1.tgz %2'
  # list example: 'file-nam$files-filter$number'
  backup(sys.argv[1], sys.argv[2], sys.argv[3:])
