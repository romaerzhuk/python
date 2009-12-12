#!/usr/bin/python
# -*- coding: utf8 -*-

from __future__ import with_statement
import sys, os, re, tempfile, hashlib, time, socket, tarfile, shutil, platform, time
   
# Засекает время выполнения команды
class StopWatch:
  def __init__(self, msg):
    self.msg = msg
    self.start = time.time()
  def stop(self):
    print "[%s]: %s sec" % (self.msg, time.time() - self.start)

# Вычисляет контрольную сумму файла в шестнадцатиричном виде
def md5sum(file):
  sw = StopWatch("md5sum -b %s" % file)
  with open(file, "rb") as fd:
    sum = hashlib.md5()
    while True:
      buf = fd.read(1024 * 1024)
      if len(buf) == 0:
        sw.stop()
        return sum.hexdigest().lower()
      sum.update(buf)

# Создаёт вложенные директории.
# Если директории уже существуют, ничего не делает
def mkdirs(path):
  #print "mkdirs(" + path + ")"
  if os.path.exists(path):
    return
  mkdirs(os.path.dirname(path))
  os.mkdir(path)

# Читает первую строку из файла
def readline(file):
  with open(file, "r") as fd:
    return fd.readline()

# Вызывает системную команду и выводит эхо на стандартный вывод
def system(command):
  sw = StopWatch(command)
  res = os.system(command)
  sw.stop()
  return res

# Проверяет, что директория - репозиторий Subversion
def issubversion(dir):
  if not os.path.isdir(dir):
    return False
  svnList = ((1, "conf"), (1, "db"), (1, "hooks"), (1, "locks"), (0, "README.txt"))
  dirSet = set(os.listdir(dir))
  for type, name in svnList:
    path = dir + '/' + name
    if name not in dirSet or type == 1 and not os.path.isdir(path) or type == 0 and not os.path.isfile(path):
      return False
  if not readline(dir + "/README.txt").startswith("This is a Subversion repository;"):
    return False
  return True

# Читает номер ревизии Subversion из файла
def readrev(file):
  prefix = "Revision: "
  with open(file, "r") as f:
    for line in f:
      if line.startswith(prefix):
        return int(line[len(prefix):])
  raise IOError("Invalid subversion info " + file)

# Запускает backup svn для указанного репозитория
def backupsvn(src, dst, name):
  info = dst + "/.info"
  dump = dst + "/.dump"
  try:
    mkdirs(dst)
    oldrev = 0
    pattern = re.compile(r"^(.+)-\d+\.\.(\d+)\.dump\.gz$")
    for f in os.listdir(dst):
      m = pattern.match(f)
      if m != None and m.group(1).startswith(name):
        oldrev = max(oldrev, int(m.group(2)))
    if system("svn info file://%s > %s" % (src, info)) != 0:
      raise IOError("Invalid subversion repository " + src)
    newrev = readrev(info)
    if newrev != oldrev:
      oldrev = oldrev + 1
      if system("svnadmin dump -r %s:%s --incremental %s | gzip > %s" \
                % (oldrev, newrev, src, dump)) != 0:
        raise IOError("Invalid subversion dumping")
      dumpname = "%s-%s..%s.dump.gz" % (name, oldrev, newrev)
      with open(dst + "/.md5", "a+b") as f:
        f.write("%s\t*%s\n" % (md5sum(dump), dumpname))
      os.rename(dump, dst + '/' + dumpname)
  finally:
    if os.path.isfile(info):
      os.remove(info)
    if os.path.isfile(dump):
      os.remove(dump)

# Запускает инкрементальный backup svn для указанной директории
# source содержит множество директорий с репозиториями Subversion
def backupsvndirs(source, dest):
  sw = StopWatch("backupsvn")
  for name in os.listdir(source):
    src = source + '/' + name
    dst = dest   + '/' + name
    if issubversion(src):
      backupsvn(src, dst, name)
  sw.stop()

if __name__ == '__main__':
  if len(sys.argv) < 2:
    print "Usage: backup-svn.py src dst"
    print "Example: backup-svn.py $HOME/src /var/backup"
  else:
    backupsvndirs(sys.argv[1], sys.argv[2])
