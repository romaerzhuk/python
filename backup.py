#!/usr/bin/python
# -*- coding: utf8 -*-

from __future__ import with_statement
import sys, os, re, time, hashlib, socket, shutil, platform, logging

def through_dirs(path, filter = None):
  """ Рекурсивно сканирует директории. Вызывает для каждой директории процедуру """
  if filter(path):
    return
  if path == '.': prefix = ''
  else: prefix = path + '/'
  for i in os.listdir(path):
    s = prefix + i
    if os.path.isdir(s):
      through_dirs(s, filter)

class StopWatch:
  """ Засекает время выполнения команды """
  def __init__(self, msg):
    self.msg = msg
    self.start = time.time()
  def stop(self):
    log.info("[%s]: %s sec", self.msg, time.time() - self.start)

def md5sum(file):
  """ Вычисляет контрольную сумму файла в шестнадцатиричном виде """
  sw = StopWatch("md5sum -b %s" % file)
  with open(file, "rb") as fd:
    sum = hashlib.md5()
    while True:
      buf = fd.read(1024 * 1024)
      if len(buf) == 0:
        sw.stop()
        return sum.hexdigest().lower()
      sum.update(buf)

def write_md5(file, md5sum, name):
  """  Пишет в открытый файл контрольную сумму
  file - открытый файл
  md5sum - сумма, в 16-ричном виде 
  name - имя файла
  """
  file.write("%s\t*%s\n" % (md5sum, name))

def load_md5(path):
  """ Возвращает множество контрольных сумм из файла и время модификации (dict, time) """
  pattern = re.compile(r"^(\S+)\s+\*(.+)$")
  lines = dict()
  if not os.path.isfile(path):
    time = -1
  else:
    time = os.path.getmtime(path)
    with open(path, "r") as fd:
      for line in fd:
        m = pattern.match(line)
        if m != None:
          lines[m.group(2)] = m.group(1).lower()
  return lines, time

def mkdirs(path):
  """  Создаёт вложенные директории.
  Если директории уже существуют, ничего не делает """
  log.debug("mkdirs(%s)", path)
  if os.path.exists(path):
    return
  mkdirs(os.path.dirname(path))
  os.mkdir(path)

def readline(file):
  """ Возвращает первую строку из файла """
  with open(file, "r") as fd:
    return fd.readline()

def system(command):
  """ Вызывает системную команду и выводит эхо на стандартный вывод """
  sw = StopWatch(command)
  res = os.system(command)
  sw.stop()
  return res

def chdir(dir):
  """ Меняет текущую директорию и выводит эхо на стандартный вывод """
  log.info("cd %s", dir)
  os.chdir(dir)

def is_subversion(dir):
  """ Проверяет, что директория - репозиторий Subversion """
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

def svnVerify(dir):
  """ Проверяет корректность файлов svn-репозиториев """
  if not is_subversion(dir):
    return False
  log.info("svn found: %s", dir)
  if system("svnadmin verify %s" % dir) != 0:
    raise IOError("Invalid subversion repository " + dir)
  return True

def bzrVerify(dir):
  """  Проверяет корректность файлов bzr-репозиториев
  Обновляет, перепаковывает """
  if ".bzr" != os.path.basename(dir):
    return False
  bzr = os.path.dirname(dir)
  log.info("bzr found: %s", bzr)
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

def gitVerify(dir):
  """  Проверяет корректность файлов git-репозиториев
  Обновляет из svn, перепаковывает """
  if ".git" != os.path.basename(dir):
    return False
  git = os.path.dirname(dir)
  log.info("git found: %s", git)
  chdir(git)
  if os.path.isdir(dir + "/svn"):
    system("git svn fetch")
  system("git gc")
  dir += "/repository/obsolete_packs"
  res = system("git fsck --full")
  if res != 0:
    raise IOError("Invalid git repository %s, result=%s" % (os.path.dirname(dir), res))
  return True

def repoVerify(dir):
  """  Создаёт резервные копии файла
  Проверяет корректность репозиториев """
  return svnVerify(dir) or bzrVerify(dir) or gitVerify(dir)

def removeFile(path):
  """ Удаляет файл """
  if os.path.isfile(path):
    os.remove(path)

class RecoveryEntry:
  """ Файл, подготовленный к восстановлению """
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

class Backup:
  """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
  def __init__(self, srcDirs, destDirs, command, suffix, num, rootDir):
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
  def full(self):
    """ Архивирует исходные файлы и клонирует копии в несколько источников """
    self.dump(False)
    self.clone()
  def dump(self, saveMd5 = True):
    """ Архивирует исходные файлы """
    for src in self.srcDirs:
      self.backup(src, saveMd5)
  def clone(self):
    """ Клонирует копии в несколько источников """
    self.recoveryDirs("")
  def backup(self, src, saveMd5):
    """ Создаёт резервные копии файла """
    try:
      if "" == src:
        return
      through_dirs(src, repoVerify)
      dst = self.destDirs[0]
      log.debug("%s, %s", dst, src)
      date = time.strftime("%Y-%m-%d")
      log.debug("dst = %s", os.path.dirname(src))
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
        lines = load_md5(md5)[0] # контрольные суммы всех файлов директории
        lines[name] = self.md5sums[path]
        with open(md5, "wb") as fd:
          for key, value in lines.items():
            write_md5(fd, value, key)
    except Exception, e:
      log.error("backup error: %s", e)
  def recoveryDirs(self, key):
    """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
    if key in self.dirSet:
      return
    log.debug("recovery dir %1s", key)
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
    log.debug("all=%1s\n  recovery=%2s\n  remove=%3s", other + list, recovery, remove)
    md5files = []
    for f in recovery:
      k = key + '/' + f.name
      if f.dir == None:
        log.error("corrupt error: %s", k)
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
            write_md5(fd, f.md5[dst], f.name)
          for name in os.listdir(dir):
            path = dir + '/' + name
            if name.endswith(".md5") and name != ".md5" and os.path.isfile(path):
              removeFile(path)
      except Exception, e:
        log.error("md5sum error: %s", e)
  def removeKey(self, key, destDirs):
    """ Удаляет файл в заданных директориях """
    for dir in destDirs:
      path = dir + key
      self.removePair(path)
  def removePair(self, path):
    """ Удаляет файл и контрольную сумму """
    if os.path.isfile(path):
      sw = StopWatch("rm %1s" % path)
      removeFile(path)
      sw.stop()
    removeFile(path + ".md5") # устаревший файл
  def copy(self, src, dst):
    """ Копирует файл """
    sw = StopWatch("cp %s %s" % (src, dst))
    try:
      mkdirs(os.path.dirname(dst))
      removeFile(dst)
      shutil.copy(src, dst)
    except Exception, e:
      log.error("copy error: %s", e)
    finally:
      sw.stop()
  def correct(self, dst, path):
    """ Проверяет контрольую сумму файла. Возвращает её, или None, если сумма не верна
       и флаг, что сумма была вычислена, а не взята из файла """
    try:
      if os.path.isfile(path):
        dir = os.path.dirname(path) + '/'
        name = os.path.basename(path)
        if dir == self.md5cache[0]:
          lines = self.md5cache[1]
          time = self.md5cache[2]
        else:
          lines, time = load_md5(dir + ".md5") # контрольные суммы всех файлов директории
          self.md5cache = (dir, lines, time)
        stored = lines.get(name)
        if stored == None:
          lines, time = load_md5(dir + name + ".md5") # устаревший файл
          stored = lines.get(name)
        if stored != None:
          if dst != self.destDirs[0] and self.checked < time:
            return stored, False
          real = md5sum(path)
          if stored == real:
            return stored, True
    except Exception, e:
      log.error("md5sum check error: %s", e)
    return None, False

def readrev(file):
  """ Читает номер ревизии Subversion из файла """
  prefix = "Revision: "
  with open(file, "r") as f:
    for line in f:
      if line.startswith(prefix):
        return int(line[len(prefix):])
  raise IOError("Invalid subversion info " + file)

class SvnDump:
  """ Запускает svnadmin dump для репозиториев Subversion """
  def __init__(self, src, dst, hostname):
    self.name = hostname + '-' + os.path.basename(src)
    self.dst = dst + '/' + hostname + '/' + self.name + '/'
    self.name += '-'
    self.lenght = len(src) + 1
    self.pattern = re.compile(r"^(.+)\.\d+-(\d+)\.svndmp\.gz$")
    through_dirs(src, self.svn_backup)
  def svn_backup(self, src):
    """ Снимает резервную копию для одиночного репозитория """
    if not is_subversion(src):
      return False
    dst = self.dst + self.name + src[self.lenght:]
    info = dst + "/.info"
    self.dump = dst + "/.dump"
    try:
      mkdirs(dst)
      oldrev = -1
      md5file = dst + "/.md5"
      self.md5 = load_md5(md5file)[0]
      prefix = self.name + os.path.basename(src)
      for name in os.listdir(dst):
        m = self.pattern.match(name)
        if m != None and m.group(1).startswith(prefix) and name in self.md5:
          if self.md5[name] == md5sum(dst + '/' + name):
            oldrev = max(oldrev, int(m.group(2)))
          else:
            del self.md5[name]
      if system("svn info file://%s > %s" % (src, info)) != 0:
        raise IOError("Invalid subversion repository " + src)
      newrev = readrev(info)
      if newrev == oldrev:
        return True
      minrev = 100
      if newrev >= minrev - 1:
        maxrev = minrev
        while newrev >= maxrev * 10 - 1:
          maxrev *= 10
        rev = -1
        step = maxrev
        while step >= minrev:
          self.svn_dump(src, dst, prefix, rev, rev + step)
          rev = rev + step
          if rev + step > newrev:
            step /= 10
        oldrev = max(oldrev, rev)
      self.svn_dump(src, dst, prefix, oldrev, newrev)
      with open(md5file, "wb") as fd:
        keys = list(self.md5.keys())
        keys.sort()
        for key in keys:
          write_md5(fd, self.md5[key], key)
      return True
    finally:
      removeFile(info)
      removeFile(self.dump)
  def svn_dump(self, src, dst, prefix, oldrev, newrev):
    """ Запускает svnadmin dump для одиночного репозитория """
    oldrev += 1
    if oldrev > newrev:
      return
    dumpname = "%s.%06d-%06d.svndmp.gz" % (prefix, oldrev, newrev)
    name = dst + '/' + dumpname
    if dumpname in self.md5 and os.path.isfile(name):
      return
    if system("svnadmin dump -r %s:%s --incremental %s | gzip > %s" \
              % (oldrev, newrev, src, self.dump)) != 0:
      raise IOError("Invalid subversion dumping")
    self.md5[dumpname] = md5sum(self.dump)
    os.rename(self.dump, name)

def hostname(index):
  """ Возвращает sys.argv[index] или имя машины """
  if len(sys.argv) > index:
    return sys.argv[index]
  return socket.gethostname()

def arg(index):
  """ Возвращает sys.arg[index], или выводит справку и завершает работу """
  if len(sys.argv) > index:
    return sys.argv[index]
  help()

def help():
  """ Выводит справку об использовании """
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

def main_backup():
  """ Выполняет резервное копирование """
  logging.basicConfig(level = logging.INFO, \
                      stream = sys.stdout, \
                      format = "%(message)s")
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

if __name__ == '__main__':
  log = logging.getLogger("backup")
  main_backup()
