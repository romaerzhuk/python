#!/usr/bin/python
# -*- coding: utf8 -*-

from __future__ import with_statement
import sys, os, re, time, hashlib, socket, platform, logging, subprocess, traceback

def through_dirs(path, dirFilter, fileFunctor=None):
  """ Рекурсивно сканирует директории.
  Вызывает для каждой директории фильтр. """
  if dirFilter(path):
    return
  if path == '.': prefix = ''
  else: prefix = path + '/'
  for i in os.listdir(path):
    s = prefix + i
    if os.path.isdir(s):
      through_dirs(s, dirFilter, fileFunctor)
    elif fileFunctor != None:
      fileFunctor(s)

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
  if not os.path.exists(path):
    os.mkdir(path)

def readline(file):
  """ Возвращает первую строку из файла """
  with open(file, "r") as fd:
    return fd.readline()

def dir_contains(dir, dirs, files):
  """ Проверяет наличие в директории списка директорий и файлов """
  for name in dirs:
    path = dir + '/' + name
    if not os.path.isdir(path):
      return False
  for name in files:
    path = dir + '/' + name
    if not os.path.isfile(path):
      return False
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
  def __init__(self, backup):
    self.md5sums = backup.new_checksum_by_path
  def found(self, dir):
    """ Проверяет, что директория - репозиторий Subversion """
    if not dir_contains(dir, ['conf', 'db', 'hooks', 'locks'], ['format', 'README.txt']):
      return False
    if not readline(dir + "/README.txt").startswith("This is a Subversion repository;"):
      return False
    return True
  def backup(self, src, dst, prefix):
    """ Снимает резервную копию для одиночного репозитория """
    mkdirs(dst)
    log.debug("backup(src=%s, dst=%s, prefix=%s)", src, dst, prefix)
    newrev = system(("svn", "info", "file://" + src), readrev)
    md5 = load_md5(dst + "/.md5")[0]
    step = minrev = 100
    while newrev >= step - 1 and step < 10000:
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

class GitBackup:
  """ Создаёт резервную копию репозитория Git """
  def __init__(self, backup):
    self.lastModified = backup.lastModified
    self.upToDate = backup.upToDate
    self.genericBackup = backup.genericBackup
    self.remote = re.compile(r'^\[remote "(.+)"\]$')
    self.svn_remote = re.compile(r'^\[svn-remote "(.+)"\]$')
  def found(self, src):
    """ Проверяет, что директория - репозиторий Git """
    found = dir_contains(src, ['.git'], [])
    if found:
      src += '/.git'
    else:
      found = dir_contains(src,
                           ['branches', 'hooks', 'info', 'objects', 'refs'],
                           ['config', 'description', 'HEAD'])
    if not found:
      return False
    log.info("git found: %s", src)
    config = src + '/config'
    log.debug("config=[%s]", config)
    remote = svn_remote = False
    remotes = {'remote': (self.remote,
                          lambda: system(['git',  'fetch', '--all'], cwd = src)),
               'svn_remote': (self.svn_remote,
                              lambda: system(['git', 'svn', 'fetch', '--all'], cwd = src))}
    with open(config, "r") as fd:
      for line in fd:
        line = line.rstrip()
        for key in remotes.keys():
          remote, commmad = remotes[key]
          matcher = remote.match(line)
          if matcher != None:
            log.debug("match('%s')=%s", line, matcher)
            commmad()
            del remotes[key]
            if len(remotes) == 0:
              return True
    return True
  def backup(self, src, dst, prefix):
    """ Создаёт резервную копию репозитория Git """
    if dir_contains(src, ['.git'], []):
      self.exclude = src + '/.git/svn'
    else:
      self.exclude = src + '/svn'
    through_dirs(src, self.lastModified, self.lastModified)
    if self.upToDate(src, dst):
      return
    system(['git', 'prune'], cwd = src)
    res = system(['git', 'fsck', '--full', '--no-progress'], cwd = src)
    if res != 0:
      raise IOError('Invalid git repository %s, result=%s' % (os.path.dirname(src), res))
    self.genericBackup(src, dst, prefix)
  def lastModified(self, path):
    """ Запоминает время последней модификации файлов """
    if self.exclude == path:
      return True
    self.lastModified(path)
    return False

class BzrBackup:
  """ Создаёт резервную копию репозитория Bzr """
  def __init__(self, backup):
    self.genericBackup = backup.genericBackup
    self.lastModified = backup.lastModified
    self.upToDate = backup.upToDate
    self.reParent = re.compile(r"^parent_location\s*=")
    self.reBound = re.compile(r"^bound\s*=\s*False")
  def found(self, src):
    """ Проверяет, что директория - репозиторий Bzr """
    if not dir_contains(src, ['.bzr'], []):
      return False
    log.info("bzr found: %s", src)
    through_dirs(src, self.update)
    return True
  def backup(self, src, dst, prefix):
    """ Создаёт резервную копию репозитория Bzr """
    through_dirs(src, self.lastModifiedIgnoreLock, self.lastModified)
    if self.upToDate(src, dst):
      return
    win = platform.system() == "Windows"
    res = system(["bzr", "check", src])
    if res != 0 and not win:
      raise IOError("Invalid bazaar repository %s, result=%s" % (src, res))
    dir = src + "/.bzr/repository/obsolete_packs"
    for file in os.listdir(dir):
      os.remove(dir + '/' + file)
    self.genericBackup(src, dst, prefix)
  def update(self, src):
    """ Обновляет репозиторий Bzr """
    if os.path.basename(src) == '.bzr':
      return True
    if not dir_contains(src, ['.bzr'], []):
      return False
    conf = src + '/.bzr/branch/branch.conf'
    if not os.path.isfile(conf):
      return False
    parent = False
    bound = True
    with open(conf) as f:
      for line in f:
        if self.reParent.match(line): parent = True
        elif self.reBound.match(line): bound = False
    if bound and os.path.isdir(src + "/.bzr/checkout"):
      system(["bzr", "update", src])
    elif parent:
      system(["bzr", "pull"], cwd = src)
    return True
  def lastModifiedIgnoreLock(self, path):
    """ Игнорирует lock при вычислении времени модификации репозитория """
    if path.endswith('/.bzr/branch/lock') or path.endswith('/.bzr/checkout/lock'):
      return
    self.lastModified(path)

class Backup:
  """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
  def __init__(self, srcDirs, destDirs, num, hostname):
    # набор способов разделить нужные копии от избыточных
    self.timeSeparator = TimeSeparator(num)
    self.separators = (self.timeSeparator, SvnSeparator())
    self.srcDirs = srcDirs
    self.destDirs = destDirs
    self.hostname = hostname
    self.dirSet = set()
    self.new_checksum_by_path = dict()
    self.checksum_by_path = dict()
    self.files_checksum_by_dir = dict()
    self.checksum_file = dict()
    self.checked = time.time() - 2 * 24 * 3600
    self.strategies = (SvnBackup(self), GitBackup(self), BzrBackup(self))
    self.commands = dict() # команды на копирование/удаление файлов разделённые на директории
    for dir in destDirs:
      self.commands[dir] = []
  def full(self):
    """ Архивирует исходные файлы и клонирует копии в несколько источников """
    self.dump()
    self.clone()
  def dump(self):
    """ Архивирует исходные файлы """
    for src in self.srcDirs:
      self.backup(src)
    dirs = dict()
    for path in self.new_checksum_by_path.keys():
      md5path = os.path.dirname(path) + "/.md5"
      lst = dirs.get(md5path)
      if lst == None:
        lst = dirs[md5path] = []
      lst.append(path)
    for md5path, lst in dirs.items():
      md5 = load_md5(md5path)[0]
      for path in lst:
        name = os.path.basename(path)
        md5[name] = self.new_checksum_by_path[path]
      with open(md5path, "wb") as fd:
        names = list(md5.keys())
        names.sort()
        for name in names:
          write_md5(fd, md5[name], name)
  def clone(self):
    """ Клонирует копии в несколько источников """
    self.recoveryDirs("")
    for dst in self.destDirs:
      for command in self.commands[dst]:
        command()
  def backup(self, src):
    """ Создаёт резервные копии директории """
    if "" == src:
      return
    self.last_modified = -1
    self.strategy_dir = []
    through_dirs(src, self.findStrategy, self.lastModified)
    prefix = self.hostname + '-' + os.path.basename(src)
    dst = self.destDirs[0] + '/' + self.hostname + '/' + prefix
    if len(self.strategy_dir) == 0:
      self.safeBackup(None, src, dst, prefix)
    else:
      length = len(src)
      for strategy, dir in self.strategy_dir:
        if len(dir) == length:
          self.safeBackup(strategy, dir, dst, prefix)
        else:
          prf = prefix + dir[length:].replace('/', '-')
          self.last_modified = -1
          self.safeBackup(strategy, dir, dst +'/' + prf, prf)
  def findStrategy(self, dir):
    """ Ищет способ резервного копирования.
        Устанавливает self.time последнее время модификации директории. """
    self.lastModified(dir)
    for strategy in self.strategies:
      if strategy.found(dir):
        self.strategy_dir.append((strategy, dir)) 
        return True
    return False
  def safeBackup(self, strategy, src, dst, prefix):
    """ Создаёт одиночную резервную копию. Перехватывает ошибки. """
    try:
      if strategy == None:
        if self.upToDate(src, dst):
          return
        self.genericBackup(src, dst, prefix)
      else:
        log.debug("strategy.backup('%s', '%s', '%s')", src, dst, prefix)
        strategy.backup(src, dst, prefix)
    except Exception, e:
      log.error("backup error: %s", e)
      traceback.print_exc()
  def genericBackup(self, src, dst, prefix):
    """ Полностью архивирует директорию, если не существует актуальной резервной копии """
    log.debug("genericBackup(%s, %s, %s)", src, dst, prefix)
    date = time.strftime("%Y-%m-%d")
    basename = os.path.basename(src)
    mkdirs(dst)
    path = dst + '/' + prefix + date + ".tar.gz"
    self.removePair(path) # удаляет устаревший файл
    self.new_checksum_by_path[path] = system(["tar", "cf", "-", basename], \
                                GzipMd5sum(path), \
                                cwd = os.path.dirname(src))
    key = path[len(self.destDirs[0]):]
    log.debug('key=%s', key)
    for dst in self.destDirs[1:]:
      self.removePair(dst + key)
  def lastModified(self, path):
    """ Устанавливает self.last_modified последнее время модификации файла. """ 
    modified = os.path.getmtime(path)
    if modified > self.last_modified:
      log.debug('lastModified %s %s', modified, path)
      self.last_modified = modified
  def upToDate(self, src, dst):
    """ Проверяет время создания последнего архива. Возвращает True, если backup не требуется """
    dst += '/'
    if not os.path.isdir(dst):
      return False
    list = []
    for name in os.listdir(dst):
      if os.path.isfile(dst + name):
        entry, index = self.recoveryEntry(name)
        if index == 0: # TimeSeparator
          log.debug('list.append(%s)', entry)
          list.append(entry)
    list = self.timeSeparator.separate(list)[0]
    log.debug('list=%s', list)
    if len(list) > 0:
      path = dst + list[0].name
      time = os.path.getmtime(path)
      checksum = self.checksum(path)[0]
      log.debug('time[%s]=%s, last_modified=%s, checksum=%s', path, time, self.last_modified, checksum)
      if time > self.last_modified and checksum != None:
        log.info('[%s] is up to date.', src)
        return True
    return False
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
            entry, index = self.recoveryEntry(name)
            fileDict[name] = entry          
            if index < 0:
              log.debug('recovery.append(%s)', name)
              recovery.append(entry)
            else:
              log.debug('lists[%s].append(%s)', index, name)
              lists[index].append(entry)
    if len(fileDict) == 0:
      return
    for (name, entry) in fileDict.items():
      for dst in self.destDirs:
        path = dst + key + '/' + name
        md5 = self.new_checksum_by_path.get(path)
        if md5 == None:
          md5, real = self.checksum(path, dst == self.destDirs[0])
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
          self.lazyCopy(f.dir, dst, k)
          self.lazyRemove(dst, k + ".md5") # устаревший файл
    for f in remove:
      for dst in self.destDirs:
        self.lazyRemovePair(dst, key + '/' + f.name)
    for dst in md5dirs:
      self.lazyWriteMd5(dst, key, md5files)
  def recoveryEntry(self, name):
    """ Возвращает созданный RecoveryEntry и индекс классификатора имён файлов """ 
    entry = RecoveryEntry(name)
    for i in xrange(len(self.separators)):
      separator = self.separators[i]
      matcher = separator.pattern.match(name)
      if matcher != None:
        separator.init(entry, matcher)
        return entry, i
    return entry, -1
  def lazyCopy(self, src, dst, key):
    """ Выполняет отложенное копирование файла """ 
    if dst != self.destDirs[0]:
      # быстрее всего копировать с 1й директории, с локального диска
      src = self.destDirs[0]
    srcPath = src + key
    dstPath = dst + key
    log.debug("lazy cp %s %s", srcPath, dstPath)
    self.commands[dst].append(lambda: self.copy(srcPath, dstPath))
  def lazyRemove(self, dst, key):
    """ Выполняет отолженное удаление файла """
    path = dst + key
    log.debug("lazy rm %s", path)
    self.commands[dst].append(lambda: removeFile(path))
  def lazyRemovePair(self, dst, key):
    """ Выполняет отолженное удаление пары файлов """
    path = dst + key
    log.debug("lazy rm %s", path)
    self.commands[dst].append(lambda: self.removePair(path))
  def lazyWriteMd5(self, dst, key, md5files):
    """ Выполняет отложенную запись контрольной суммы """
    log.debug("lazy md5sum -b * > %s%s/.md5", dst, key)
    self.commands[dst].append(lambda: self.writeMd5(dst, key, md5files))    
  def writeMd5(self, dst, key, md5files):
    """ Пишет контрольные суммы в файл """
    try:
      dir  = dst + key 
      path = dir + "/.md5"
      removeFile(path)
      with open(path, "wb") as fd:
        for f in md5files:
          write_md5(fd, f.md5[dst], f.name)
      for name in os.listdir(dir):
        path = dir + '/' + name
        if name.endswith(".md5") and name != ".md5" and os.path.isfile(path):
          removeFile(path)
    except Exception, e:
      log.error("new_checksum_by_path error: %s", e)
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
  def checksum(self, path, real_only = True):
    """ Проверяет контрольую сумму файла. Возвращает её, или None, если сумма не верна
        и флаг, что сумма была вычислена, а не взята из файла """
    try:
      stored, time = self.storedChecksum(path)
      if time == None or not real_only and self.checked < time:
        return (stored, False)
      real = md5sum(path)
      if stored != real:
        stored = None
      self.checksum_by_path[path] = (stored, None)
      return (stored, True)
    except Exception, e:
      log.error("new_checksum_by_path check error: %s", e)
      self.checksum_by_path[path] = (None, None)
      return (None, False)
  def storedChecksum(self, path):
    """ Возвращает контрольную сумму из файла и время расчёта контрольной суммы """
    result = self.checksum_by_path.get(path)
    if result != None:
      return result
    if not os.path.isfile(path):
       self.checksum_by_path[path] = result = (None, None)
       return result
    dir = os.path.dirname(path) + '/'
    lines, time = self.checksumFiles(dir)
    name = os.path.basename(path)
    stored = lines.get(name)
    self.checksum_by_path[path] = result = (stored, time)
    return result
  def checksumFiles(self, dir):
    """ Возвращает контрольные суммы директории из файла .md5 """
    result = self.files_checksum_by_dir.get(dir)
    if result == None:
      self.files_checksum_by_dir[dir] = result = load_md5(dir + ".md5") 
    return result

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
  global log
  log = logging.getLogger("backup")
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
  main_backup()
