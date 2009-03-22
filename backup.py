#!/usr/bin/python
# -*- coding: utf8 -*-

import sys, os, re, time, hashlib, socket, tarfile, shutil

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
  sum = hashlib.md5()
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
  
# Проверяет корректность файлов svn-репозиториев
def svnVerify(dir):
  for rep in os.listdir(dir):
    if os.path.isdir(dir + '/' + rep) and os.system("svnadmin verify %1s/%2s" % (dir, rep)) != 0:
      raise IOError("Invalid subversion repository " + rep)

# Проверяет корректность файлов bzr-репозиториев
def bzrVerify(dir):
  if ".bzr" != os.path.basename(dir):
    return True
  bzr = os.path.dirname(dir)
  if os.path.isdir(dir + "/checkout"):
    os.system("bzr update %1s" % bzr)
  if os.path.isdir(dir + "/repository"): 
    if os.system("bzr check %1s" % bzr) != 0:
      raise IOError("Invalid bazaar repository %1s" % bzr)
    if os.system("bzr pack %1s" % bzr) != 0:
      raise IOError("Bazaar pack error %1s" % bzr)
  return False

# Создаёт резервные копии файла
# Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий
class Backup:
  def __init__(self, destDirs, srcDirs, command, suffix, num, rootDir):
    self.md5Pattern = re.compile(r"^(\S+)\s+\*(.+)$")
    self.removePattern = re.compile(r'\d\d\d\d-\d\d-\d\d')
    self.set = set()
    self.destDirs = destDirs
    self.command = command
    self.suffix = suffix
    self.num = num * 2 # должны быть ещё файлы с контрольными суммами
    self.rootDir = rootDir

    for dir in destDirs:
      self.clear(dir)
    for src in srcDirs:
      if "" != src:
        if "svn" == os.path.basename(src):
          svnVerify(src)
        if "bzr" == os.path.basename(src):
          through_dirs(src, lambda x: None, bzrVerify)
        self.backup(destDirs[0], src)
    for self.dir in destDirs:
      self.recoveryDir("")
    for dir in destDirs:
      self.clear(dir)
  # Удаляет из директорий устаревшие файлы
  def clear(self, dir):
    try:
      through_dirs(dir, self)
    except Exception, e:
      print "clear error:", e
  # Удаляет из директории устаревшие файлы. Оставляет последние num-файлов
  def __call__(self, path):
    r = self.removePattern
    list = filter(lambda i: r.search(i) != None, os.listdir(path))
    list.sort(lambda x, y: ((r.search(y).group(0) >= r.search(x).group(0)) << 1) - 1)
    #print list[self.num:]
    for i in list[self.num:]:
      os.remove(path + '/' + i)
  # Создаёт резервные копии файла
  def backup(self, dir, src):
      try:
        #print dir, src
        date = time.strftime("%Y-%m-%d")
        host = socket.gethostname()
        self.dir = dir
        #print "src.dir =", os.path.dirname(src)
        os.chdir(os.path.dirname(src))
        src = os.path.basename(src)
        dir = '/' + self.rootDir + '/' + host + '-' + src
        mkdirs(self.path(dir))
        key = dir + '/' + host + '-' + src + date + '.' + self.suffix
        path = self.path(key)
        command = self.command % (os.path.normpath(path), src)
        if os.path.exists(path):
          os.remove(path)
        self.set.add(key)
        #print "command =", command
        os.system(command)
        md5sumCreate(path)
        self.clear(self.path(dir))
        
        #print "copy backup dirs..."
        destDirs = set(self.destDirs)
        destDirs.remove(self.dir)
        #print "for self.dif in", destDirs 
        for self.dir in destDirs:
          #print "copy backup", self.dir
          self.copy(path, self.path(key))
          self.clear(self.path(dir))
      except Exception, e:
        print "backup error:", e
  # Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий 
  def recoveryDir(self, key):
    path = self.path(key)
    if not os.path.isdir(path):
      return
    for name in os.listdir(path):
      k = key + '/' + name
      path = self.path(k)
      if os.path.isdir(path):
        self.recoveryDir(k)
      else:
        if not k.endswith(".md5") and not (k in self.set):
          self.set.add(k)
          self.recoveryFile(name, k)
  # Восстанавливает повреждённй или отсутствующий файл из зеркальных копий 
  def recoveryFile(self, name, key):        
    src = None
    dstSet = set()
    for dir in self.destDirs:
      dst = dir + key
      if not self.correct(name, dst):
        dstSet.add(dst)
      elif src == None:
        src = dst
    if src == None:
      print "corrupted error:", key
    else:
      for dst in dstSet: 
        print "recover %1s from %2s" % (dst, src)
        self.copy(src, dst)
  # Копирует файл с контрольой суммой
  def copy(self, src, dst):
    try:
      #print "copy", src, dst
      mkdirs(os.path.dirname(dst))
      shutil.copy(src, dst)
      shutil.copy(self.md5(src), self.md5(dst))
    except Exception, e:
      print "copy error:", e
  # Проверяет контрольую сумму файла
  def correct(self, name, path):
    try:
      md5 = self.md5(path)
      if not os.path.exists(path) or not os.path.exists(md5):
        return False
      line = file(md5).readline()
      #print self.dir, ',', k, " line =", line
      m = self.md5Pattern.match(line)
      if m == None:
        return False
      real = md5sum(path).hexdigest()
      #print self.dir, ',', k, " real =", real
      return real == m.group(1) and name == m.group(2)
    except Exception, e:
      print "md5sum check error:", e
      return False
  # Возвращает полный путь файла
  def path(self, key):
    return self.dir + key
  # Возвращает имя файла с контрольной суммой
  def md5(self, path):
    return path + ".md5"
              
if __name__ == '__main__':
  if len(sys.argv) < 6:
    print "Usage: backup.py destDirs srcDirs archivingCommand fileSuffix numberOfFiles [rootDir]" 
    print "Example: backup.py /var/backup $HOME/src 'tar czf %1s %2s' tar.gz 3" 
  else:
    if len(sys.argv) >= 7:
      root = sys.argv[6]
    else:
      root = socket.gethostname()
    Backup(sys.argv[1].split(","), sys.argv[2].split(","), sys.argv[3], sys.argv[4], int(sys.argv[5]), root)
