#!/usr/bin/python
# -*- coding: utf8 -*-

import sys, os, re, time, md5, socket, tarfile

# Удаляет из директории устаревшие файлы. Оставляет последние num-файлов
class Remover:
  def __init__(self, num):
    self.num = num * 2 # должны быть ещё файлы с контрольными суммами
  def __call__(self,path):
    r=re.compile(r'\d\d\d\d-\d\d-\d\d')
    list=filter(lambda i: r.search(i)!=None, os.listdir(path))
    list.sort(lambda x, y: ((r.search(y).group(0)>=r.search(x).group(0))<<1)-1)
    #print list[self.num:]
    for i in list[self.num:]:
      os.remove(path+'/'+i)

# Рекурсивно сканирует директорию. Вызывает для каждой директории процедуру
def through_dirs(path, proc=None, fileFilter=None):
  if path=='.': prefix=''
  else: prefix=path+'/'
  if fileFilter==None or fileFilter(path):
    if proc==None:
      print path
    else:
      proc(path)
  for i in os.listdir(path):
    s=prefix+i
    if os.path.isdir(s):
      through_dirs(s,proc,fileFilter)

# Вычисляет контрольную сумму файла. Результат пишет в файл.md5
def md5sum(file):
  sum = md5.new()
  fd  = open(file, "rb")
  while 1:
    buf = fd.read(8192)
    if len(buf) == 0:
      break
    sum.update(buf)
  fd.close()
  fd = open(file + ".md5", "w")
  fd.write("%s\t*%s\n" % (sum.hexdigest(), os.path.basename(file)))

# Создаёт резервную копию файла
def backup(dest, src, remove, command, suffix):
  #print dest, src 
  through_dirs(dest, remove)
  host = socket.gethostname()
  date = time.strftime("%Y-%m-%d")
  #print "dir =", os.path.dirname(src)
  os.chdir(os.path.dirname(src))
  src = os.path.basename(src)
  name = dest+"/"+host+"/"+host+"-"+src+"/"+host+"-"+src+date+"."+suffix
  command = command % (name, src)
  #print "command =", command
  os.system(command)
  md5sum(name)
  through_dirs(dest, remove)

# Проверяет корректность файлов svn-репозиториев
def svnVerify(dir):
  for rep in os.listdir(dir):
    if os.system("svnadmin verify %1s/%2s" % (dir, rep)) != 0:
      raise "Invalid subversion repository " + rep 

# Проверяет корректность файлов bzr-репозиториев
def bzrVerify(dir):
  if ".bzr" != os.path.basename(dir):
    return 1
  dir = os.path.dirname(dir)
  os.system("bzr update %1s" % dir)
  if os.system("bzr check %1s" % dir) != 0:
    raise "Invalid bazaar repository " + dir
  return 0

def main(destDirs, srcDirs, command, suffix, num):
  remove = Remover(num)
  for src in srcDirs:
    if "svn" == os.path.basename(src):
      svnVerify(src)
    if "bzr" == os.path.basename(src):
      through_dirs(src, lambda x: None, bzrVerify)
    for dest in destDirs:
      backup(dest, src, remove, command, suffix)

if __name__=='__main__':
  if len(sys.argv) <= 4:
    print "Usage: backup.py destDirs srcDirs archivingCommand fileSuffix numberOfFiles" 
    print "Example: backup.py /var/backup $HOME/src 'tar czf %1s %2s' tar.gz 3" 
  else:
    main(sys.argv[1].split(","), sys.argv[2].split(","), sys.argv[3], sys.argv[4], int(sys.argv[5]))
