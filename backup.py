#!/usr/bin/python3
# -*- coding: utf8 -*-

from __future__ import with_statement
import sys, os, re, time, hashlib, socket, platform, logging, subprocess, traceback, smtplib, json, functools
from email.mime.text import MIMEText

def through_dirs(path, dirFilter, fileFunctor=None):
  """ Рекурсивно сканирует директории.
  Вызывает для каждой директории фильтр. """
  if dirFilter(path):
    return
  if path == '.': prefix = ''
  else: prefix = path + '/'
  for i in os.listdir(path):
    s = prefix + i
    if os.path.isdir(os.path.realpath(s)):
      through_dirs(s, dirFilter, fileFunctor)
    elif fileFunctor != None:
      fileFunctor(s)

class StopWatch:
  """ Засекает время выполнения команды """
  def __init__(self, msg):
    self.msg = msg
    self.start = time.time()
  def stop(self):
    log.info("[%s]: %1.3f sec", self.msg, time.time() - self.start)

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
  file.write(bytes("%s\t*%s\n" % (md5sum, name), 'UTF-8'))

def load_md5(path):
  """ Возвращает множество контрольных сумм из файла и время модификации (dict, time) """
  pattern = re.compile(r"^(\S+)\s+\*(.+)$")
  lines = dict()
  if not os.path.isfile(path):
    time = -1
  else:
    time = os.path.getmtime(path)
    with open(path, encoding='UTF-8') as fd:
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
  with open(file, encoding='UTF-8') as fd:
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
  except Exception as e:
    if platform.system() != "Windows":
      raise e
    p = subprocess.Popen(["cmd.exe", "/c"] + command, stdout = subprocess.PIPE, stdin = stdin, cwd = cwd)
  if reader == None:
    for line in p.stdout:
      print(line.rstrip())
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
    list.sort(key=functools.cmp_to_key(self.cmp))
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
    list.sort(key=functools.cmp_to_key(self.cmp))
    recovery, remove = [], []
    for i in range(len(list)):
      ei = list[i]
      if ei.recovery:
        recovery.append(ei)
        if ei.dir != None:
          for j in range(i + 1, len(list)):
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
  def found(self, src):
    """ Проверяет, что директория - репозиторий Git """
    found = dir_contains(src, ['.git'], [])
    git = src
    if found:
      src += '/.git'
    else:
      found = dir_contains(src,
                           ['branches', 'hooks', 'objects', 'refs'],
                           ['config', 'HEAD'])
    if not found:
      return False
    log.info("git found: %s", git)
    config = src + '/config'
    log.debug("config=[%s]", config)
    return True
  def backup(self, src, dst, prefix):
    """ Создаёт резервную копию репозитория Git """
    if dir_contains(src, ['.git'], []):
      git = src + '/.git'
    else:
      git = src
    log.info("\nbackup git: %s", git)
    remotes = system_hidden(['git', 'config', '--list'], cwd = src, reader = self.readRemotes)
    for name in remotes['svn-remote']:
      system(['git', 'svn', 'fetch', name], cwd = src)
    mirrors = []
    for name in remotes['remote']:
      remote = remotes['remote'][name]
      mirror = remote.get('mirror')
      log.debug('remote.%s.mirror=%s', name, mirror)
      if mirror != 'true':
        system(['git',  'fetch', '--prune', name], cwd = src)
      else:
        mirrors.append(name)
    for name in mirrors:
      system(['git',  'push', name], cwd = src)
    self.excludes = set([git + '/svn', git + '/FETCH_HEAD', git + '/subgit', git + '/refs/svn/map'])
    through_dirs(src, self.lastModifiedWithExcludes, self.lastModifiedWithExcludes)
    if self.upToDate(src, dst):
      return
    system(['git', 'prune'], cwd = src)
    res = system(['git', 'fsck', '--full', '--no-progress'], cwd = src)
    if res != 0:
      raise IOError('Invalid git repository %s, result=%s' % (os.path.dirname(src), res))
    self.genericBackup(src, dst, prefix)
  def lastModifiedWithExcludes(self, path):
    """ Запоминает время последней модификации файлов """
    if path in self.excludes:
      return True
    self.lastModified(path)
    return False
  def readRemotes(self, config):
    """ Читает конфигурацию репозитория """
    remote = re.compile(r'(remote|svn-remote)\.([^\.]+)\.([^=]+)=(.*)')
    remotes = {'remote': {}, 'svn-remote': {}}
    for line in config:
      matcher = remote.match(line.decode('utf-8'))
      if matcher != None:
        type  = matcher.group(1)
        name  = matcher.group(2)
        key   = matcher.group(3)
        value = matcher.group(4)
        remotes[type].setdefault(name, {})
        remotes[type][name][key] = value
    log.debug('remotes=%s', remotes)
    return remotes

class Backup:
  """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
  def help(self):
    """ Выводит справку об использовании """
    print("Usage: backup.py command [options]")
    print("\ncommands:")
    print("\tfull srcDirs destDirs numberOfFiles -- dumps, clones and checks md5 sums")
    print("\tdump srcDirs destDirs [-h hostname] -- dumps source directories and writes md5 check sums")
    print("\tclone destDirs numberOfFiles -- checks md5 sums and clone archived files")
    print("\tgit srcDirs -- fetch srcDir Git repositories from remotes and push into remotes when --mirror=push")
    print("\nExamples:")
    print("\tbackup.py full $HOME/src /local/backup,/remote/backup 3")
    print("\tbackup.py dump $HOME/src,$HOME/bin /var/backup")
    print("\tbackup.py clone /local/backup,/remote/backup2 5")
    print("\tbackup.py git $HOME/src,$HOME/bin")
    print()
    print("Optional config file $HOME/.config/backup/backup.cfg:")
    print("{")
    print('  "hostname": "myhost",')
    print('  "smtp_host": "smtp.mail.ru",')
    print('  "smtp_port": 425,')
    print('  "smtp_user": "user",')
    print('  "smtp_password": "password",')
    print('  "fromaddr": "backup@mail.ru",')
    print('  "toaddrs": "admin@mail.ru, admin2@mail.ru",')
    print('  "log_level": "DEBUG",')
    print('  "log_format": "%(levelname)5s %(lineno)3d %(message)s"')
    print("}")
    sys.exit()
  def __init__(self, config):
    """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
    self.arg_index = 1
    command = self.arg()
    num = None
    if "full" == command:
      method = self.full
      srcDirs = self.arg()
      destDirs = self.arg()
      num = int(self.arg())
    elif "dump" == command:
      method = self.dump
      srcDirs = self.arg()
      destDirs = self.arg()
    elif "clone" == command:
      method = self.clone
      srcDirs = ""
      destDirs = self.arg()
      num = int(self.arg())
    elif "git" == command:
      method = self.git
      srcDirs = self.arg()
      destDirs = None
    else:
      self.help()
    self.hostname = config.get('hostname')
    if self.hostname == None:
      self.hostname = socket.gethostname()
    self.smtp_host = config.get('smtp_host')
    # набор способов разделить нужные копии от избыточных
    self.timeSeparator = TimeSeparator(num)
    self.separators = (self.timeSeparator, SvnSeparator())
    self.srcDirs = srcDirs.split(',')
    log.debug("srcDirs=%s", self.srcDirs)
    self.destDirs = destDirs.split(',') if destDirs != None else []
    log.debug("destDirs=%s", self.destDirs)
    self.dirSet = set()
    self.new_checksum_by_path = dict()
    self.checksum_by_path = dict()
    self.files_checksum_by_dir = dict()
    self.checksum_file = dict()
    self.checked = time.time() - 2 * 24 * 3600
    self.strategies = (SvnBackup(self), GitBackup(self))
    self.commands = dict() # команды на копирование/удаление файлов разделённые на директории
    self.errors = []
    for dir in self.destDirs:
      self.commands[dir] = []
    log.debug("self.commands=%s", self.commands)
    try:
      method()
    except:
      self.error("%s", traceback.format_exc())
    if len(self.errors) > 0:
      smtp_port = config.get('smtp_port')
      server = smtplib.SMTP_SSL(self.smtp_host)
      user = config.get('smtp_user')
      password = config.get('smtp_password')
      server.login(user, password)
      msg = MIMEText('\n'.join(self.errors), 'plain', 'utf-8')
      msg['Subject'] = "backup error: " + self.hostname
      msg['From'] = config.get('fromaddr')
      msg['To'] = config.get('toaddrs')
      server.send_message(msg)
      server.quit()

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
      md5path = os.path.dirname(path) + '/.md5'
      lst = dirs.get(md5path)
      if lst == None:
        lst = dirs[md5path] = []
      lst.append(path)
    for md5path, lst in dirs.items():
      md5 = load_md5(md5path)[0]
      for path in lst:
        name = os.path.basename(path)
        md5[name] = self.new_checksum_by_path[path]
      with open(md5path, 'wb') as fd:
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
  def git(self):
    """ Выполняет fetch Git-репозиториев, и push, если настроен mirror push """
    for src in self.srcDirs:
      self.backup(src)
  def backup(self, src):
    """ Создаёт резервные копии директории """
    log.debug('backup(self, src=[%s]); self.destDirs=[%s]', src, self.destDirs)
    if '' == src:
      return
    self.last_modified = -1
    self.strategy_dir = []
    through_dirs(src, self.findStrategy, self.lastModified)
    prefix = self.hostname + '-' + os.path.basename(src)
    dst = self.destDirs[0] + '/' + self.hostname + '/' + prefix if len(self.destDirs) > 0 else None
    log.debug('backup: dst=[%s]', dst)
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
          dstPrf = dst + '/' + prf if dst != None else None
          log.debug('backup: dstPrf=[%s]', dstPrf)
          self.safeBackup(strategy, dir, dstPrf, prf)
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
    except Exception as e:
      self.error("backup error:%s\n%s", e, traceback.format_exc())
  def genericBackup(self, src, dst, prefix):
    """ Полностью архивирует директорию, если не существует актуальной резервной копии """
    log.debug("genericBackup(%s, %s, %s)", src, dst, prefix)
    if dst == None:
      log.debug('genericBackup: ignore dst=[%s]', dst)
      return
    date = time.strftime("%Y-%m-%d")
    basename = os.path.basename(src)
    mkdirs(dst)
    path = dst + '/' + prefix + date + ".tar.gz"
    self.remove(path)
    self.new_checksum_by_path[path] = system(["tar", "cf", "-", basename], \
                                GzipMd5sum(path), \
                                cwd = os.path.dirname(src))
    key = path[len(self.destDirs[0]):]
    log.debug('key=%s', key)
    for dst in self.destDirs[1:]:
      self.removePath(dst + key)
  def lastModified(self, path):
    """ Устанавливает self.last_modified последнее время модификации файла. """ 
    if not os.path.isfile(path):
      return
    modified = os.path.getmtime(path)
    if modified > self.last_modified:
      log.debug('lastModified %s %s', modified, path)
      self.last_modified = modified
  def upToDate(self, src, dst):
    """ Проверяет время создания последнего архива. Возвращает True, если backup не требуется """
    if dst == None:
      log.debug('dst=[%s] is up date.', dst)
      return True
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
    log.debug('for dst in %s', self.destDirs)
    for dst in self.destDirs:
      log.debug('for dst=%s in %s', dst, self.destDirs)
      path = dst + key
      if not os.path.isdir(path):
        log.debug('continue')
        continue
      log.debug('for name in %s', os.listdir(path))
      for name in os.listdir(path):
        log.debug('for name=%s in os.listdir.path(%s)', name, path)
        k = key + '/' + name
        path = dst + k
        if os.path.isdir(path):
          log.debug('enter into self.recoveryDirs(%s)', k)
          self.recoveryDirs(k)
          log.debug('leave from self.recoveryDirs(%s)', k)
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
    log.debug('for (name, entry) in in %s', fileDict)
    for (name, entry) in fileDict.items():
      log.debug(' for (name=%s, entry=%s) in in %s', name, entry, fileDict)
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
    log.debug('for i in in range=%s', range(len(self.separators)))
    for i in range(len(self.separators)):
      rec, old = self.separators[i].separate(lists[i])
      recovery += rec
      remove += old
    log.debug("all=%s\n  recovery=%s\n  remove=%s", recovery + remove, recovery, remove)
    md5files = []
    for rec in recovery:
      k = key + '/' + rec.name
      if rec.dir == None:
        self.error("corrupt error: %s", k)
      else:
        md5files.append(rec)
        for dst in rec.list:
          self.lazyCopy(rec, dst, k)
    for f in remove:
      for dst in self.destDirs:
        self.lazyRemove(dst, key + '/' + rec.name)
    for dst in md5dirs:
      self.lazyWriteMd5(dst, key, md5files)
  def recoveryEntry(self, name):
    """ Возвращает созданный RecoveryEntry и индекс классификатора имён файлов """ 
    entry = RecoveryEntry(name)
    for i in range(len(self.separators)):
      separator = self.separators[i]
      matcher = separator.pattern.match(name)
      if matcher != None:
        separator.init(entry, matcher)
        return entry, i
    return entry, -1
  def lazyCopy(self, rec, dst, key):
    """ Выполняет отложенное копирование файла """
    log.debug("lazy cp %s%s %s%s", rec.dir, key, dst, key)
    self.commands[dst].append(lambda: self.copy(rec, dst, key))
  def lazyRemove(self, dst, key):
    """ Выполняет отолженное удаление файла """
    path = dst + key
    log.debug("lazy rm %s", path)
    self.commands[dst].append(lambda: self.remove(path))
  def lazyWriteMd5(self, dst, key, md5files):
    """ Выполняет отложенную запись контрольной суммы """
    log.debug("lazy md5sum -b * > %s%s/.md5", dst, key)
    self.commands[dst].append(lambda: self.writeMd5(dst, key, md5files))
  def writeMd5(self, dst, key, md5files):
    """ Пишет контрольные суммы в файл """
    dir  = dst + key 
    path = dir + "/.md5"
    self.safeWrite(path, lambda fd: self.doWriteMd5(fd, dst, md5files), lambda: "md5sum -b %s/*" % dst + key)
  def doWriteMd5(self, fd, dst, md5files):
    """ Пишет контрольные суммы в файл """
    for rec in md5files:
      if dst in rec.md5:
        write_md5(fd, rec.md5[dst], rec.name)
  def safeWrite(self, file, write, name):
    try:
      tmp = file + ".tmp"
      removeFile(tmp)
      mkdirs(os.path.dirname(file))
      with open(tmp, "wb") as fd:
        write(fd)
      removeFile(file)
      os.rename(tmp, file)
      return 1
    except Exception as e:
      self.error("%s error: %s\n%s", name(), e, traceback.format_exc())
      return 0
    finally:
      self.safeRemove(tmp)
  def safeRemove(self, path):
    """ удаляет файл с подавление исключений """
    try:
      self.remove(path)
    except Exception as e:
      self.error("[rm %s] error: %s\n%s", path, e, traceback.format_exc())
  def remove(self, path):
    """ Удаляет файл """
    if os.path.isfile(path):
      sw = StopWatch("rm %1s" % path)
      removeFile(path)
      sw.stop()
  def copy(self, rec, dstDir, key):
    """ Копирует файл """
    # быстрее всего копировать с 1й директории, с локального диска
    srcDir = rec.dir if dstDir == self.destDirs[0] else self.destDirs[0]
    src = srcDir + key
    dst = dstDir + key
    sw = StopWatch("cp %s %s" % (src, dst))
    if self.safeWrite(dst, lambda out: self.doCopy(out, src), lambda: "cp %s %s" % (src, dst)):
      rec.md5[dstDir] = rec.md5[rec.dir]
    sw.stop()
  def doCopy(self, out, src):
    with open(src, 'rb') as input:
      while True:
        buf = input.read(1024 * 1024)
        if len(buf) == 0:
          break
        out.write(buf)
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
    except Exception as e:
      self.error("new_checksum_by_path check error: %s", e)
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
  def error(self, format, *args):
    """ Пишет сообщение в лог. Добавляет сообщение для отправки email """
    log.error(format, *args)
    if (self.smtp_host != None):
      self.errors.append(format % args)
  def arg(self):
    """ Возвращает sys.arg[self.arg_index], или выводит справку и завершает работу """
    if len(sys.argv) > self.arg_index:
      arg = sys.argv[self.arg_index]
      self.arg_index += 1
      return arg
    self.help()

def readrev(stdout):
  """ Читает номер ревизии Subversion из стандартного вывода """
  prefix = b"Revision: "
  for line in stdout:
    if line.startswith(prefix):
      return int(line[len(prefix):])
  raise IOError("Invalid subversion info")

def main_backup():
  """ Выполняет резервное копирование """
  global log
  sw = StopWatch("backup")
  try:
    with open(os.path.expanduser('~/.config/backup/backup.cfg'), encoding='UTF-8') as input:
      config = json.load(input)
  except IOError:
    config = {}
  log = logging.getLogger("backup")
  if config.get('log_level') == 'DEBUG':
    level = logging.DEBUG
  else:
    level = logging.INFO
  format = config.get('log_format')
  if format == None:
    #format = "%(levelname)5s %(lineno)3d %(message)s"
    format = "%(message)s"
  logging.basicConfig(level = level, stream = sys.stdout, format = format)
  sys.setrecursionlimit(100)
  Backup(config)
  sw.stop()

if __name__ == '__main__':
  main_backup()
