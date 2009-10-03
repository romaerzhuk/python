#!/usr/bin/python
# -*- coding: utf8 -*-

import sys, os, re, time, hashlib, socket, tarfile, shutil, platform, time

# Рекурсивно сканирует директорию. Вызывает для каждой директории процедуру
def through_dirs(path, proc = None, fileFilter = None):
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

# Закрывает файл с проверкой на None
def close(fd):
  if fd != None:
    fd.close()

# Засекает время выполнения команды
class StopWatch:
  def __init__(self, msg):
    self.msg = msg
    self.start = time.time()
  def stop(self):
    print "[%1s]: %2s sec" % (self.msg, time.time() - self.start)

# Вычисляет контрольную сумму файла в шестнадцатиричном виде
def md5sum(file):
  fd = open(file, "rb")
  try:
    sum = hashlib.md5()
    while True:
      buf = fd.read(1024 * 1024)
      if len(buf) == 0:
        return sum.hexdigest().lower()
      sum.update(buf)
  finally:
    close(fd)

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
  fd = open(file, "r")
  try:
    return fd.readline()
  finally:
    close(fd)

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

# Проверяет корректность файлов svn-репозиториев
def svnVerify(dir):
  svnList = ((1, "conf"), (1, "db"), (1, "hooks"), (1, "locks"), (0, "README.txt"))
  dirSet = set(os.listdir(dir))
  for type, name in svnList:
    path = dir + '/' + name
    if name not in dirSet or type == 1 and not os.path.isdir(path) or type == 0 and not os.path.isfile(path):
      return True
  if not readline(dir + "/README.txt").startswith("This is a Subversion repository;"):
    return True
  print "svn found:", dir
  if system("svnadmin verify %1s" % dir) != 0:
    raise IOError("Invalid subversion repository " + dir)
  return False

# Проверяет корректность файлов bzr-репозиториев
# Обновляет, перепаковывает
def bzrVerify(dir):
  if ".bzr" != os.path.basename(dir):
    return True
  bzr = os.path.dirname(dir)
  print "bzr found:", bzr
  conf = dir + "/branch/branch.conf"
  if os.path.isfile(conf):
    f = open(conf)
    try:
      reParent = re.compile(r"^parent_location\s*=")
      reBound = re.compile(r"^bound\s*=\s*False")
      parent = False
      bound = True
      for line in f:
        if reParent.match(line): parent = True
        elif reBound.match(line): bound = False
    finally:
      f.close()
    if bound and os.path.isdir(dir + "/checkout"):
      system("bzr update %1s" % bzr)
    elif parent:
      chdir(bzr)
      system("bzr pull")
  if os.path.isdir(dir + "/repository"):
    notWin = platform.system() != "Windows"
    res = system("bzr check %1s" % bzr)
    if res != 0 and notWin:
      raise IOError("Invalid bazaar repository %1s, result=%2s" % (bzr, res))
    packs = dir + "/repository/packs"
    if os.path.isdir(packs) and len(os.listdir(packs)) > 1:
      res = system("bzr pack %1s" % bzr)
      if res != 0 and notWin:
        raise IOError("Bazaar pack error %1s, result=%2s" % (bzr, res))
    dir += "/repository/obsolete_packs"
    for file in os.listdir(dir):
      os.remove(dir + '/' + file)
  return False

# Проверяет корректность файлов git-репозиториев
# Обновляет из svn, перепаковывает
def gitVerify(dir):
  if ".git" != os.path.basename(dir):
    return True
  git = os.path.dirname(dir)
  print "git found:", git
  chdir(git)
  if os.path.isdir(dir + "/svn"):
    system("git svn fetch")
  system("git gc")
  dir += "/repository/obsolete_packs"
  res = system("git fsck --full")
  if res != 0:
    raise IOError("Invalid git repository %1s, result=%2s" % (os.path.dirname(dir), res))
  return False

# Создаёт резервные копии файла
# Проверяет корректность репозиториев
def repoVerify(dir):
  return not (svnVerify(dir) and bzrVerify(dir) and gitVerify(dir))

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
    return 'name=%1s, dir=%2s, list=%3s]' % (self.name, self.dir, self.list)

# Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий
class Backup:
  def __init__(self, destDirs, srcDirs, command, suffix, num, rootDir):
    self.md5Pattern = re.compile(r"^(\S+)\s+\*(.+)$")
    self.removePattern = re.compile(r'\d\d\d\d-\d\d-\d\d')
    self.destDirs = destDirs
    self.command = command
    self.suffix = suffix
    self.num = num
    self.rootDir = rootDir
    self.dirSet = set()
    self.md5sums = dict()
    self.md5cache = (None, None)
    for src in srcDirs:
      if "" != src:
        through_dirs(src, lambda x: None, repoVerify)
        self.backup(src)
    self.recoveryDirs("")
  # Создаёт резервные копии файла
  def backup(self, src):
      try:
        dst = self.destDirs[0]
        #print dst, src
        date = time.strftime("%Y-%m-%d")
        host = socket.gethostname()
        #print "dst =", os.path.dirname(src)
        chdir(os.path.dirname(src))
        src = os.path.basename(src)
        dir = '/' + self.rootDir + '/' + host + '-' + src
        mkdirs(dst + dir)
        key = dir + '/' + host + '-' + src + date + '.' + self.suffix
        path = dst + key
        command = self.command % (os.path.normpath(path), src)
        self.removePair(path)
        system(command)
        self.md5sums[path] = md5sum(path)
        self.removeKey(key, self.destDirs[1:])
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
          md5 = self.correct(path)
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
        print "corrupt error: %1s" % k
      else:
        md5files.append(f)
        for dst in f.list:
          f.md5[dst] = f.md5[f.dir]
          self.copy(f.dir + k, dst + k)
          self.removeFile(dst + k + ".md5") # устаревший файл
    for f in remove:
      self.removeKey(key + '/' + f.name, self.destDirs)
    for dst in md5dirs:
      fd = None
      try:
        dir = dst + key
        name = dir + "/.md5"
        self.removeFile(name) # иначе глючит QNAP 109
        fd = open(name, "wb")
        for f in md5files:
          fd.write("%s\t*%s\n" % (f.md5[dst], f.name))
        for name in os.listdir(dir):
          path = dir + '/' + name
          if name.endswith(".md5") and name != ".md5" and os.path.isfile(path):
            self.removeFile(path)
      except Exception, e:
        print "md5sum error:", e
      finally:
        close(fd)

  # Удаляет файл в заданных директориях
  def removeKey(self, key, destDirs):
    for dir in destDirs:
      path = dir + key
      self.removePair(path)
  # Удаляет файл и контрольную сумму
  def removePair(self, path):
    if os.path.isfile(path):
      sw = StopWatch("rm %1s" % path)
      self.removeFile(path)
      sw.stop()
    self.removeFile(path + ".md5") # устаревший файл
  # Удаляет файл
  def removeFile(self, path):
    if os.path.isfile(path):
      os.remove(path)
  # Копирует файл
  def copy(self, src, dst):
    sw = StopWatch("cp %1s %2s" % (src, dst))
    try:
      mkdirs(os.path.dirname(dst))
      shutil.copy(src, dst)
    except Exception, e:
      print "copy error:", e
    finally:
      sw.stop()
  # Проверяет контрольую сумму файла. Возвращает её, или None, если сумма не верна
  def correct(self, path):
    try:
      if not os.path.isfile(path):
        return None
      dir = os.path.dirname(path) + '/'
      name = os.path.basename(path)
      if dir == self.md5cache[0]:
        lines = self.md5cache[1]
      else:
        lines = self.loadMd5(dir + ".md5") # контрольные суммы всех файлов директории
        self.md5cache = (dir, lines)
      stored = lines.get(name)
      if stored == None:
        stored = self.loadMd5(dir + name + ".md5").get(name) # устаревший файл
      if stored == None:
        return None
      real = md5sum(path)
      if stored == real:
        return real
      return None
    except Exception, e:
      print "md5sum check error:", e
      return None
  # Загружает множество контрольных сумм из файла
  def loadMd5(self, path):
    lines = dict()
    if os.path.isfile(path):
      fd = open(path, "r")
      try:
        for line in fd:
          m = self.md5Pattern.match(line)
          if m != None:
            lines[m.group(2)] = m.group(1).lower()
      finally:
        close(fd)
    return lines

if __name__ == '__main__':
  if len(sys.argv) < 6:
    print "Usage: backup.py destDirs srcDirs archivingCommand fileSuffix numberOfFiles [rootDir]"
    print "Example: backup.py /var/backup $HOME/src 'tar czf %1s %2s' tar.gz 3"
  else:
    if len(sys.argv) >= 7:
      root = sys.argv[6]
    else:
      root = socket.gethostname()
    sw = StopWatch("backup")
    Backup(sys.argv[1].split(","), sys.argv[2].split(","), sys.argv[3], sys.argv[4], int(sys.argv[5]), root)
    sw.stop()
