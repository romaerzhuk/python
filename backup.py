#!/usr/bin/python
# -*- coding: utf8 -*-

import sys, os, re, time, md5, socket, tarfile, shutil

# Удаляет из директории устаревшие файлы. Оставляет последние num-файлов
class Remover:
  def __init__(self, num):
    self.num = num * 2 # должны быть ещё файлы с контрольными суммами
  def __call__(self, path):
    r = re.compile(r'\d\d\d\d-\d\d-\d\d')
    list = filter(lambda i: r.search(i) != None, os.listdir(path))
    list.sort(lambda x, y: ((r.search(y).group(0) >= r.search(x).group(0)) << 1) - 1)
    #print list[self.num:]
    for i in list[self.num:]:
      os.remove(path + '/' + i)

# Рекурсивно сканирует директорию. Вызывает для каждой директории процедуру
def through_dirs(path, proc=None, fileFilter=None):
  if path == '.': prefix = ''
  else: prefix = path + '/'
  if fileFilter == None or fileFilter(path):
    if proc == None:
      print path
    else:
      proc(path)
  for i in os.listdir(path):
    s = prefix + i
    if os.path.isdir(s):
      through_dirs(s, proc, fileFilter)

# Вычисляет контрольную сумму файла. Результат пишет в файл.md5
def md5sumCreate(file):
  fd = open(file + ".md5", "wb")
  fd.write("%s\t*%s\n" % (md5sum(file).hexdigest(), os.path.basename(file)))

# Вычисляет контрольную сумму файла
def md5sum(file):
  sum = md5.new()
  fd = open(file, "rb")
  while True:
    buf = fd.read(1024 * 1024)
    if len(buf) == 0:
      break
    sum.update(buf)
  fd.close()
  return sum

# Создаёт вложенные директории.
# Если директории уже существуют, ничего не делает
def mkdirs(path):
  #print "mkdirs(" + path + ")"
  if os.path.exists(path):
    return
  mkdirs(os.path.dirname(path))
  os.mkdir(path)
  
# Создаёт резервную копию файла
def backup(dest, src, remove, command, suffix, root):
  try:
    #print dest, src
    through_dirs(dest, remove)
    date = time.strftime("%Y-%m-%d")
    host = socket.gethostname()
    #print "dir =", os.path.dirname(src)
    os.chdir(os.path.dirname(src))
    src = os.path.basename(src)
    name = dest + '/' + root + '/' + host + '-' + src
    mkdirs(name)
    name += '/' + host + '-' + src + date + '.' + suffix
    command = command % (name, src)
    #print "command =", command
    os.system(command)
    md5sumCreate(name)
    through_dirs(dest, remove)
  except Exception, e:
    print e

# Проверяет корректность файлов svn-репозиториев
def svnVerify(dir):
  for rep in os.listdir(dir):
    if os.system("svnadmin verify %1s/%2s" % (dir, rep)) != 0:
      raise "Invalid subversion repository " + rep 

# Проверяет корректность файлов bzr-репозиториев
def bzrVerify(dir):
  if ".bzr" != os.path.basename(dir):
    return True
  dir = os.path.dirname(dir)
  os.system("bzr update %1s" % dir)
  if os.system("bzr check %1s" % dir) != 0:
    raise "Invalid bazaar repository " + dir
  return False

# Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий
class MirrorRecovery:
  def __init__(self, destDirs):
    self.pattren = re.compile(r"^(\S+)\s+\*(.+)$")
    self.set = set()
    self.destDirs = set(destDirs)
    for self.dir in destDirs:
      self.files("")
  def files(self, key):
    path = self.path(key)
    for i in os.listdir(path):
      k = key + '/' + i
      path = self.path(k)
      if os.path.isdir(path):
        self.files(k)
      else:
        if not k.endswith(".md5") and not (k in self.set) and self.correct(i, path):
          self.set.add(k)
          #print "self.destDirs - self.dir =", (self.destDirs - set([self.dir]))
          for dir in (self.destDirs - set([self.dir])):
            dst = dir + k
            if not self.correct(i, dst):
              print "recover %1s from %2s" % (dst, self.dir)
              mkdirs(os.path.dirname(dst))
              shutil.copy(path, dst)
              shutil.copy(self.md5(path), self.md5(dst))
  def correct(self, name, path):
    try:
      md5 = self.md5(path)
      if not os.path.exists(path) or not os.path.exists(md5):
        return False
      line = file(md5).readline()
      #print self.dir, ',', k, " line =", line
      m = self.pattren.match(line)
      if m == None:
        return False
      real = md5sum(path).hexdigest()
      #print self.dir, ',', k, " real =", real
      return real == m.group(1) and name == m.group(2)
    except Exception, e:
      print "md5sum check error:", e
      return False
  def path(self, key):
    return self.dir + key
  def md5(self, path):
    return path + ".md5"
              
            
def main(destDirs, srcDirs, command, suffix, num, host):
  remove = Remover(num)
  for src in srcDirs:
    if "svn" == os.path.basename(src):
      svnVerify(src)
    if "bzr" == os.path.basename(src):
      through_dirs(src, lambda x: None, bzrVerify)
    for dest in destDirs:
      backup(destDir, src, remove, command, suffix, host)
  MirrorRecovery(destDirs)
    
if __name__ == '__main__':
  if len(sys.argv) < 6:
    print "Usage: backup.py destDirs srcDirs archivingCommand fileSuffix numberOfFiles [rootDir]" 
    print "Example: backup.py /var/backup $HOME/src 'tar czf %1s %2s' tar.gz 3" 
  else:
    if len(sys.argv) >= 7:
      root = sys.argv[6]
    else:
      root = socket.gethostname()
    main(sys.argv[1].split(","), sys.argv[2].split(","), sys.argv[3], sys.argv[4], int(sys.argv[5]), root)
