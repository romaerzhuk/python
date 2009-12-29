#!/usr/bin/python
# -*- coding: utf8 -*-

from __future__ import with_statement
import sys, os, re, time, hashlib, socket, platform, logging, subprocess, zlib

def through_dirs(path, filter):
  """ Рекурсивно сканирует директории.
  Вызывает для каждой директории фильтр. """
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

def md5sum(path, input = None, out = None):
  """ Вычисляет контрольную сумму файла в шестнадцатиричном виде """
  if input == None:
    if not os.path.isfile(path):
      return None
    sw = StopWatch("md5sum -b %s" % path)
    with open(path, "rb") as input:
      sum = md5sum(path, input)
      sw.stop()
      return sum
  sum = hashlib.md5()
  while True:
    buf = input.read(1024 * 1024)
    if len(buf) == 0:
      return sum.hexdigest().lower()
    sum.update(buf)
    if out != None:
      out.write(buf)

class GzipMd5sum:
  """ Сжимает поток, считает контрольную сумму сжатого потока, и пишет в файл """
  def __init__(self, path):
    self.path = path
  def __call__(self, input):
    with open(self.path, "wb") as out:
      return system_hidden(["gzip"], lambda stdout: md5sum(None, stdout, out), input)

def write_md5(file, md5sum, name):
  """  Пишет в открытый файл контрольную сумму
  file   - открытый файл
  md5sum - сумма, в 16-ричном виде 
  name   - имя файла
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
      system(["bzr", "update", bzr])
    elif parent:
      system(["bzr", "pull"], cwd = bzr)
  if os.path.isdir(dir + "/repository"):
    notWin = platform.system() != "Windows"
    res = system(["bzr", "check", bzr])
    if res != 0 and notWin:
      raise IOError("Invalid bazaar repository %s, result=%s" % (bzr, res))
    packs = dir + "/repository/packs"
    if os.path.isdir(packs) and len(os.listdir(packs)) > 1:
      res = system(["bzr", "pack", bzr])
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
  git_repo = os.path.dirname(dir)
  log.info("git found: %s", git_repo)
  if os.path.isdir(dir + "/svn"):
    system(["git", "svn", "fetch"], cwd = git_repo)
  system(["git", "gc"], cwd = git_repo)
  dir += "/repository/obsolete_packs"
  res = system(["git", "fsck", "--full"], cwd = git_repo)
  if res != 0:
    raise IOError("Invalid git repository %s, result=%s" % (os.path.dirname(dir), res))
  return True

def removeFile(path):
  """ Удаляет файл, если он существует """
  if os.path.isfile(path):
    os.remove(path)

def system(command, reader = None, stdin = None, cwd = None):
  """ Запускает процесс.
  Вызывает процедуру для чтения стандартного вывода.
  Возвращает результат процедуры.
  Выводит на экран команду
   """
  sw = StopWatch(' '.join(command))
  res = system_hidden(command, reader, stdin, cwd)
  sw.stop()
  return res

def system_hidden(command, reader = None, stdin = None, cwd = None):
  """ Запускает процесс.
  Вызывает процедуру для чтения стандартного вывода.
  Возвращает результат процедуры """
  try:
    p = subprocess.Popen(command, stdout = subprocess.PIPE, stdin = stdin, cwd = cwd)
  except Exception, e:
    if platform.system() != "Windows":
      raise e
    p = subprocess.Popen(["cmd.exe", "/c"] + command, stdout = subprocess.PIPE, stdin = stdin, cwd = cwd)
  if reader == None:
    for line in p.stdout:
      print line.rstrip()
    return p.wait()
  res = reader(p.stdout)
  # дочитывает стандартный вывод, если что-то осталось
  for line in p.stdout:
    pass
  p.wait()
  return res

class RepoVerify:
  """ Проверяет корректность репозиториев """
  def __init__(self):
    self.svn = False
  def __call__(self, dir):
    self.svn = is_subversion(dir)
    return self.svn or bzrVerify(dir) or gitVerify(dir)

class RecoveryEntry:
  """ Файл, подготовленный к восстановлению """
  def __init__(self, name):
    self.name = name       # имя файла
    self.md5 = dict()      # контрольная сумма файла в соответствущей директории
    self.dir = None        # имя директории с корректным файлом
    self.list = []         # список директорий, куда нужно восстанавливать файл
  def __repr__(self):
    return "Entry(name=%s, dir=%s, list=%s)" % (self.name, self.dir, self.list)

class TimeSeparator:
  """ Отделяет нужные копии от избыточных по дате создания """
  def __init__(self, num):
    self.num = num
    self.pattern = re.compile(r"^.+(\d\d\d\d-\d\d-\d\d)\..+$")
  def init(self, entry, matcher):
    """ Инициализирует Entry """
    entry.date = matcher.group(1)
  def separate(self, list):
    """ Сортирует список по времени в обратном порядке, оставляет первые self.num элементов """
    list.sort(self.cmp)
    return list[:self.num], list[self.num:]
  def cmp(self, e1, e2):
    """ Сравнивает файлы по дате: e1.date <= e2.date """
    if e1.dir != None:
      if e2.dir == None:
        return - 1
    elif e2.dir != None:
      return 1
    return ((e1.date <= e2.date) << 1) - 1

class SvnSeparator:
  """ Отделяет ненужные копии с перекрывающимися диапазонами ревизий svn """
  def __init__(self):
    self.pattern = re.compile(r"^(.+)\.(\d+)-(\d+)\.svndmp\.gz$")
  def init(self, entry, matcher):
    """ Инициализирует Entry """
    entry.recovery = True
    entry.start = int(matcher.group(2))
    entry.stop = int(matcher.group(3))
  def separate(self, list):
    """ Разделяет перекрывающиеся диапазоны ревизий """
    list.sort(self.cmp)
    recovery, remove = [], []
    for i in xrange(len(list)):
      ei = list[i]
      if ei.recovery:
        recovery.append(ei)
        if ei.dir != None:
          for j in xrange(i + 1, len(list)):
            ej = list[j]
            if ej.recovery and ei.stop >= ej.stop:
              ej.recovery = False
              remove.append(ej)
            elif ei.stop < ej.start:
              break
    return recovery, remove
  def cmp(self, e1, e2):
    """ Сортирует по ревизиям """
    cmp = e1.start - e2.start
    if cmp != 0:
      return cmp
    return e2.stop - e1.stop

class SvnBackup:
  """ Запускает svnadmin dump для репозиториев Subversion
  Сохраняет в self.md5sums подсчитанные контрольные суммы """
  def __init__(self, src, dst, hostname, md5sums):
    self.name = hostname + '-' + os.path.basename(src)
    self.dst = dst + '/' + hostname + '/' + self.name
    self.md5sums = md5sums
    self.length = len(src)
  def backup(self, src):
    """ Снимает резервную копию для одиночного репозитория """
    if not is_subversion(src):
      return False
    dst = self.dst
    prefix = self.name
    if len(src) > self.length:
      prefix += src[self.length:].replace('/', '-')
      dst = self.dst + '/' + prefix
    log.debug("backup(src=%s, dst=%s, prefix=%s)", src, dst, prefix)
    mkdirs(dst)
    newrev = system(("svn", "info", "file://" + src), readrev)
    md5 = load_md5(dst + "/.md5")[0]
    step = minrev = 100
    while newrev >= step - 1:
      step *= 10
    oldrev = -1
    while True:
        while oldrev + step > newrev:
          step /= 10
        if step < minrev:
          break
        rev = oldrev + step
        self.dump(src, dst, prefix, oldrev, rev, md5)
        oldrev = rev
    self.dump(src, dst, prefix, oldrev, newrev, md5)
    return True
  def dump(self, src, dst, prefix, oldrev, newrev, md5):
    """ Запускает svnadmin dump для одиночного репозитория """
    oldrev += 1
    log.debug("svn_dump(%s, %s, %s)", prefix, oldrev, newrev)
    if oldrev > newrev:
      return
    dumpname = "%s.%06d-%06d.svndmp.gz" % (prefix, oldrev, newrev)
    path = dst + '/' + dumpname
    sum = md5.get(dumpname)
    if sum != None and sum == md5sum(path):
      self.md5sums[path] = sum
      return
    self.md5sums[path] = system(["svnadmin", "dump", "-r", \
      "%d:%d" % (oldrev, newrev), "--incremental", src], \
       GzipMd5sum(path))

class Backup:
  """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
  def __init__(self, srcDirs, destDirs, num, hostname):
    # набор способов разделить нужные копии от избыточных
    self.separators = (TimeSeparator(num), SvnSeparator())
    self.srcDirs = srcDirs
    self.destDirs = destDirs
    self.hostname = hostname
    self.dirSet = set()
    self.md5sums = dict()
    self.md5cache = (None, None)
    self.checked = time.time() - 2 * 24 * 3600
  def full(self):
    """ Архивирует исходные файлы и клонирует копии в несколько источников """
    self.dump()
    self.clone()
  def dump(self):
    """ Архивирует исходные файлы """
    for src in self.srcDirs:
      self.backup(src)
    dirs = dict()
    for path in self.md5sums.keys():
      md5path = os.path.dirname(path) + "/.md5"
      lst = dirs.get(md5path)
      if lst == None:
        lst = dirs[md5path] = []
      lst.append(path)
    for md5path, lst in dirs.items():
      md5 = load_md5(md5path)[0]
      for path in lst:
        name = os.path.basename(path)
        md5[name] = self.md5sums[path]
      with open(md5path, "wb") as fd:
        names = list(md5.keys())
        names.sort()
        for name in names:
          write_md5(fd, md5[name], name)
  def clone(self):
    """ Клонирует копии в несколько источников """
    self.recoveryDirs("")
  def backup(self, src):
    """ Создаёт резервные копии директории """
    try:
      if "" == src:
        return
      self.subversion = False
      through_dirs(src, self.repoVerify)
      dst = self.destDirs[0]
      if self.subversion:
        svn = SvnBackup(src, dst, self.hostname, self.md5sums)
        through_dirs(src, svn.backup)
      else:
        self.generic_backup(src, dst)
    except Exception, e:
      log.error("backup error: %s", e)
  def repoVerify(self, dir):
    """ Проверяет корректность репозиториев.
    Устанавливает self.subversion, если обнаруживает репозиторий Subversion-а"""
    self.subversion = self.subversion or is_subversion(dir)
    return self.subversion or bzrVerify(dir) or gitVerify(dir)
  def generic_backup(self, src, dst):
    """ Полностью архивирует директорию """
    log.debug("generic_backup(%s, %s)", src, dst)
    date = time.strftime("%Y-%m-%d")
    log.debug("dst = %s", os.path.dirname(src))
    basename = os.path.basename(src)
    dir = '/' + self.hostname + '/' + self.hostname + '-' + basename
    name = self.hostname + '-' + basename + date + ".tar.gz"
    key = dir + '/' + name
    dir = dst + dir
    mkdirs(dir)
    path = dst + key
    self.removePair(path) # удаляет устаревший файл
    self.md5sums[path] = system(["tar", "cf", "-", basename], \
                                GzipMd5sum(path), \
                                cwd = os.path.dirname(src))
    self.removeKey(key, self.destDirs[1:])
  def recoveryDirs(self, key):
    """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий
    Удаляет устаревшие копии """
    if key in self.dirSet:
      return
    log.debug("recovery dir %1s", key)
    self.dirSet.add(key)
    lists, recovery, remove = ([], []), [], []
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
            entry = None
            for i in xrange(len(self.separators)):
              separator = self.separators[i]
              matcher = separator.pattern.match(name)
              if matcher != None:
                fileDict[name] = entry = RecoveryEntry(name)
                separator.init(entry, matcher)
                lists[i].append(entry)
                break
            if entry == None:
              recovery.append(entry)
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
    for i in xrange(len(self.separators)):
      rec, old = self.separators[i].separate(lists[i])
      recovery += rec
      remove += old
    log.debug("all=%s\n  recovery=%s\n  remove=%s", recovery + remove, recovery, remove)
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
        log.error("md5sums error: %s", e)
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
      with open(src, 'rb') as input:
        with open(dst, 'wb') as out:
          while True:
            buf = input.read(1024 * 1024)
            if len(buf) == 0:
              break
            out.write(buf)
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
      log.error("md5sums check error: %s", e)
    return None, False

def readrev(stdout):
  """ Читает номер ревизии Subversion из стандартного вывода """
  prefix = "Revision: "
  for line in stdout:
    if line.startswith(prefix):
      return int(line[len(prefix):])
  raise IOError("Invalid subversion info")

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
  print "\tfull srcDirs destDirs numberOfFiles [hostname] -- dumps, clones and checks md5 sums"
  print "\tdump srcDirs destDirs [hostname] -- dumps source directories and writes md5 check sums"
  print "\tclone destDirs numberOfFiles -- checks md5 sums and clone archived files"
  print "\nExamples:"
  print "\tbackup.py full $HOME/src /local/backup,/remote/backup 3"
  print "\tbackup.py dump $HOME/src,$HOME/bin /var/backup myhost"
  print "\tbackup.py clone /local/backup,/remote/backup2 5"
  sys.exit()

def main_backup():
  """ Выполняет резервное копирование """
  logging.basicConfig(level = logging.INFO, \
                      stream = sys.stdout, \
                      format = "%(message)s")
  sw = StopWatch("backup")
  command = arg(1)
  if "full" == command:
    Backup(arg(2).split(","), arg(3).split(","), int(arg(4)), hostname(5)).full()
  elif "dump" == command:
    Backup(arg(2).split(","), arg(3).split(","), None, hostname(4)).dump()
  elif "clone" == command:
    Backup([], arg(2).split(","), int(arg(3)), None).clone()
  else:
    help()
  sw.stop()

if __name__ == '__main__':
  log = logging.getLogger("backup")
  main_backup()
