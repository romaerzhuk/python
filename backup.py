#!/usr/bin/python
# -*- coding: utf8 -*-

from __future__ import with_statement
import sys, os, re, time, hashlib, socket, shutil, platform

# Рекурсивно сканирует директорию. Вызывает для каждой директории процедуру
def through_dirs(path, filter = None):
  if filter == None:
    print path
  elif filter(path):
    return
  if path == '.': prefix = ''
  else: prefix = path + '/'
  for i in os.listdir(path):
    s = prefix + i
    if os.path.isdir(s):
      through_dirs(s, filter)

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

# Пишет в открытый файл контрольную сумму
# file - открытый файл
# md5sum - сумма, в 16-ричном виде 
# name - имя файла
def writeMd5(file, md5sum, name):
  file.write("%s\t*%s\n" % (md5sum, name))

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

# Меняет текущую директорию и выводит эхо на стандартный вывод
def chdir(dir):
  print "cd", dir
  os.chdir(dir)

# Проверяет, что директория - репозиторий Subversion
def isSubversion(dir):
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

# Проверяет корректность файлов svn-репозиториев
def svnVerify(dir):
  if not isSubversion(dir):
    return False
  print "svn found:", dir
  if system("svnadmin verify %s" % dir) != 0:
    raise IOError("Invalid subversion repository " + dir)
  return True

# Проверяет корректность файлов bzr-репозиториев
# Обновляет, перепаковывает
def bzrVerify(dir):
  if ".bzr" != os.path.basename(dir):
    return False
  bzr = os.path.dirname(dir)
  print "bzr found:", bzr
  conf = dir + "/branch/branch.conf"
  if os.path.isfile(conf):
    reParent = re.compile(r"^parent_location\s*=")
    reBound = re.compile(r"^bound\s*=\s*False")
    parent = False
    bound = True
    with open(conf) as f:
      for line in f:
        if reParent.match(line): parent = True
        elif reBound.match(line): bound = False
    if bound and os.path.isdir(dir + "/checkout"):
      system("bzr update %s" % bzr)
    elif parent:
      chdir(bzr)
      system("bzr pull")
  if os.path.isdir(dir + "/repository"):
    notWin = platform.system() != "Windows"
    res = system("bzr check %s" % bzr)
    if res != 0 and notWin:
      raise IOError("Invalid bazaar repository %s, result=%s" % (bzr, res))
    packs = dir + "/repository/packs"
    if os.path.isdir(packs) and len(os.listdir(packs)) > 1:
      res = system("bzr pack %s" % bzr)
      if res != 0 and notWin:
        raise IOError("Bazaar pack error %s, result=%s" % (bzr, res))
    dir += "/repository/obsolete_packs"
    for file in os.listdir(dir):
      os.remove(dir + '/' + file)
  return True

# Проверяет корректность файлов git-репозиториев
# Обновляет из svn, перепаковывает
def gitVerify(dir):
  if ".git" != os.path.basename(dir):
    return False
  git = os.path.dirname(dir)
  print "git found:", git
  chdir(git)
  if os.path.isdir(dir + "/svn"):
    system("git svn fetch")
  system("git gc")
  dir += "/repository/obsolete_packs"
  res = system("git fsck --full")
  if res != 0:
    raise IOError("Invalid git repository %s, result=%s" % (os.path.dirname(dir), res))
  return True

# Создаёт резервные копии файла
# Проверяет корректность репозиториев
def repoVerify(dir):
  return svnVerify(dir) or bzrVerify(dir) or gitVerify(dir)

# Удаляет файл
def removeFile(path):
  if os.path.isfile(path):
    os.remove(path)

# Файл, подготовленный к восстановлению
class RecoveryEntry:
  def __init__(self, name):
    self.name = name  # имя файла
    self.md5 = dict() # контрольная сумма файла в соответствущей директории
    self.dir = None   # имя директории с корректным файлом
    self.list = []    # список директорий, куда нужно восстанавливать файл
  def __cmp__(self, entry):
    if self.dir != None:
      if entry.dir == None:
        return - 1
    elif entry.dir != None:
      return 1
    return ((entry.date >= self.date) << 1) - 1
  def __repr__(self):
    return 'name=%s, dir=%s, list=%s]' % (self.name, self.dir, self.list)

# Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий
class Backup:
  def __init__(self, srcDirs, destDirs, command, suffix, num, rootDir):
    self.md5Pattern = re.compile(r"^(\S+)\s+\*(.+)$")
    self.removePattern = re.compile(r'\d\d\d\d-\d\d-\d\d')
    self.srcDirs = srcDirs
    self.destDirs = destDirs
    self.command = command
    self.suffix = suffix
    self.num = num
    self.rootDir = rootDir
    self.dirSet = set()
    self.md5sums = dict()
    self.md5cache = (None, None)
    self.checked = time.time() - 2 * 24 * 3600
  # Архивирует исходные файлы и клонирует копии в несколько источников
  def full(self):
    self.dump(False)
    self.clone()
  # Архивирует исходные файлы
  def dump(self, saveMd5 = True):
    for src in self.srcDirs:
      self.backup(src, saveMd5)
  # Клонирует копии в несколько источников
  def clone(self):
    self.recoveryDirs("")
  # Создаёт резервные копии файла
  def backup(self, src, saveMd5):
    try:
      if "" == src:
        return
      through_dirs(src, repoVerify)
      dst = self.destDirs[0]
      #print dst, src
      date = time.strftime("%Y-%m-%d")
      #print "dst =", os.path.dirname(src)
      chdir(os.path.dirname(src))
      src = os.path.basename(src)
      dir = '/' + self.rootDir + '/' + self.rootDir + '-' + src
      name = self.rootDir + '-' + src + date + '.' + self.suffix
      key = dir + '/' + name
      dir = dst + dir
      mkdirs(dir)
      path = dst + key
      command = self.command % (os.path.normpath(path), src)
      self.removePair(path)
      system(command)
      self.md5sums[path] = md5sum(path)
      self.removeKey(key, self.destDirs[1:])
      if saveMd5:
        md5 = dir + "/.md5"
        lines = self.loadMd5(md5)[0] # контрольные суммы всех файлов директории
        lines[name] = self.md5sums[path]
        with open(md5, "wb") as fd:
          for key, value in lines.items():
            writeMd5(fd, value, key)
    except Exception, e:
      print "backup error:", e
  # Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий 
  def recoveryDirs(self, key):
    if key in self.dirSet:
      return
    #print "recovery dir %1s" % key
    self.dirSet.add(key)
    list, other = [], []
    fileDict = dict()
    md5dirs = set()
    for dst in self.destDirs:
      path = dst + key
      if not os.path.isdir(path):
        continue
      for name in os.listdir(path):
        k = key + '/' + name
        path = dst + k
        if os.path.isdir(path):
          self.recoveryDirs(k)
        elif os.path.isfile(path):
          if name.endswith(".md5"):
            if name != ".md5":
              md5dirs.add(dst)
          elif not name in fileDict:
            fileDict[name] = entry = RecoveryEntry(name)
            matcher = self.removePattern.search(name)
            if matcher == None:
              other.append(entry)
            else:
              list.append(entry)
              entry.date = matcher.group(0)
    if len(fileDict) == 0:
      return
    for (name, entry) in fileDict.items():
      for dst in self.destDirs:
        path = dst + key + '/' + name
        md5 = self.md5sums.get(path)
        if md5 == None:
          md5, real = self.correct(dst, path)
          if real:
            md5dirs.add(dst)
        else:
          md5dirs.add(dst)
        if md5 == None:
          md5dirs.add(dst)
          entry.list.append(dst)
        else:
          if entry.dir == None:
            entry.dir = dst
          entry.md5[dst] = md5
    list.sort()
    recovery = other + list[:self.num]
    remove = list[self.num:]
    #print " all=%1s\n  recovery=%2s\n  remove=%3s" % (other + list, recovery, remove)
    md5files = []
    for f in recovery:
      k = key + '/' + f.name
      if f.dir == None:
        print "corrupt error: %s" % k
      else:
        md5files.append(f)
        for dst in f.list:
          f.md5[dst] = f.md5[f.dir]
          self.copy(f.dir + k, dst + k)
          removeFile(dst + k + ".md5") # устаревший файл
    for f in remove:
      self.removeKey(key + '/' + f.name, self.destDirs)
    for dst in md5dirs:
      try:
        dir = dst + key
        name = dir + "/.md5"
        removeFile(name)
        with open(name, "wb") as fd:
          for f in md5files:
            writeMd5(fd, f.md5[dst], f.name)
          for name in os.listdir(dir):
            path = dir + '/' + name
            if name.endswith(".md5") and name != ".md5" and os.path.isfile(path):
              removeFile(path)
      except Exception, e:
        print "md5sum error:", e
  # Удаляет файл в заданных директориях
  def removeKey(self, key, destDirs):
    for dir in destDirs:
      path = dir + key
      self.removePair(path)
  # Удаляет файл и контрольную сумму
  def removePair(self, path):
    if os.path.isfile(path):
      sw = StopWatch("rm %1s" % path)
      removeFile(path)
      sw.stop()
    removeFile(path + ".md5") # устаревший файл
  # Копирует файл
  def copy(self, src, dst):
    sw = StopWatch("cp %s %s" % (src, dst))
    try:
      mkdirs(os.path.dirname(dst))
      removeFile(dst)
      shutil.copy(src, dst)
    except Exception, e:
      print "copy error:", e
    finally:
      sw.stop()
  # Проверяет контрольую сумму файла. Возвращает её, или None, если сумма не верна
  # и флаг, что сумма была вычислена, а не взята из файла 
  def correct(self, dst, path):
    try:
      if os.path.isfile(path):
        dir = os.path.dirname(path) + '/'
        name = os.path.basename(path)
        if dir == self.md5cache[0]:
          lines = self.md5cache[1]
          time = self.md5cache[2]
        else:
          lines, time = self.loadMd5(dir + ".md5") # контрольные суммы всех файлов директории
          self.md5cache = (dir, lines, time)
        stored = lines.get(name)
        if stored == None:
          lines, time = self.loadMd5(dir + name + ".md5") # устаревший файл
          stored = lines.get(name)
        if stored != None:
          if dst != self.destDirs[0] and self.checked < time:
            return stored, False
          real = md5sum(path)
          if stored == real:
            return stored, True
    except Exception, e:
      print "md5sum check error:", e
    return None, False
  # Возвращает множество контрольных сумм из файла и время модификации 
  def loadMd5(self, path):
    lines = dict()
    if not os.path.isfile(path):
      time = -1
    else:
      time = os.path.getmtime(path)
      with open(path, "r") as fd:
        for line in fd:
          m = self.md5Pattern.match(line)
          if m != None:
            lines[m.group(2)] = m.group(1).lower()
    return lines, time

# Читает номер ревизии Subversion из файла
def readrev(file):
  prefix = "Revision: "
  with open(file, "r") as f:
    for line in f:
      if line.startswith(prefix):
        return int(line[len(prefix):])
  raise IOError("Invalid subversion info " + file)

# Запускает svnadmin dump для репозиториев
class SvnDump:
  def __init__(self, src, dst, hostname):
    self.dst = dst + '/' + hostname + '/' + hostname + '-' + os.path.basename(src) + '/'
    self.lenght = len(src) + 1
    self.pattern = re.compile(r"^(.+)\.\d+-(\d+)\.svndmp\.gz$")
    through_dirs(src, self.dump)
  def dump(self, dir):
    if not isSubversion(dir):
      return False
    dst = self.dst + dir[self.lenght:]
    info = dst + "/.info"
    dump = dst + "/.dump"
    try:
      mkdirs(dst)
      oldrev = 0
      name = os.path.basename(dir)
      for f in os.listdir(dst):
        m = self.pattern.match(f)
        if m != None and m.group(1).startswith(name):
          oldrev = max(oldrev, int(m.group(2)))
      if system("svn info file://%s > %s" % (dir, info)) != 0:
        raise IOError("Invalid subversion repository " + dir)
      newrev = readrev(info)
      if newrev != oldrev:
        oldrev = oldrev + 1
        if system("svnadmin dump -r %s:%s --incremental %s | gzip > %s" \
                  % (oldrev, newrev, dir, dump)) != 0:
          raise IOError("Invalid subversion dumping")
        dumpname = "%s.%06d-%06d.svndmp.gz" % (name, oldrev, newrev)
        with open(dst + "/.md5", "a+b") as fd:
            writeMd5(fd, md5sum(dump), dumpname)
        os.rename(dump, dst + '/' + dumpname)
      return True
    finally:
      removeFile(info)
      removeFile(dump)

# Возвращает sys.argv[index] или имя машины 
def hostname(index):
  if len(sys.argv) > index:
    return sys.argv[index]
  return socket.gethostname()

# Возвращает sys.arg[index], или выводит справку и завершает работу
def arg(index):
  if len(sys.argv) > index:
    return sys.argv[index]
  help()

# Выводит справку об использовании
def help():
  print "Usage: backup.py command [options]"
  print "\ncommands:"
  print "\tfull srcDirs destDirs archivingCommand fileSuffix numberOfFiles [rootDir] -- dumps, clones and checks md5 sums"
  print "\tdump srcDirs destDirs archivingCommand fileSufix [rootDir] -- dumps source directories and writes md5 check sums"
  print "\tsvn-dump srcDir destDir [rootDir] -- dumps svn directories and writes md5 check sums"
  print "\tclone destDirs numberOfFiles -- checks md5 sums and clone archived files"
  print "\nExamples:"
  print "\tbackup.py full $HOME/src /local/backup,/remote/backup 'tar czf %s %s' tar.gz 3"
  print "\tbackup.py dump $HOME/src,$HOME/bin /var/backup '7z a %s %s' 7z myhost"
  print "\tbackup.py clone /local/backup,/remote/backup2 5"
  print "\tbackup.py svn-dump /var/svn /var/backup"
  sys.exit()

if __name__ == '__main__':
  sw = StopWatch("backup")
  command = arg(1)
  if "full" == command:
    Backup(arg(2).split(","), arg(3).split(","), arg(4), arg(5), int(arg(6)), hostname(7)).full()
  elif "dump" == command:
    Backup(arg(2).split(","), arg(3).split(","), arg(4), arg(5), None, hostname(6)).dump()
  elif "clone" == command:
    Backup([], arg(2).split(","), None, None, int(arg(3)), None).clone()
  elif "svn-dump" == command:
    SvnDump(arg(2), arg(3), hostname(4))
  else:
    help()
  sw.stop()
