#!/usr/bin/python
# -*- coding: utf8 -*-
from __future__ import with_statement
import sys, os, re, platform, logging, subprocess

def system(command, reader = None, stdin = sys.stdin, cwd = None):
  """ Запускает процесс.
  Вызывает процедуру для чтения стандартного вывода.
  Возвращает результат процедуры """
  if reader == None:
    stdout, res = sys.stdout, None
  else:
    stdout = subprocess.PIPE
  try:
    p = subprocess.Popen(command, stdout = stdout, stdin = stdin, stderr = sys.stderr, cwd = cwd)
  except Exception, e:
    if platform.system() != 'Windows':
      raise e
    p = subprocess.Popen(['cmd.exe', '/c'] + command, stdout = stdout, stdin = stdin, stderr = sys.stderr, cwd = cwd)
  if reader != None:
    res = reader(p.stdout)
    # дочитывает стандартный вывод, если что-то осталось
    for line in p.stdout:
      pass
  p.wait()
  return res

class Main:
  def __init__(self):
    """ Выполняет команду svn с заменой trunk:, branch:, tag:  на соответствующие URL-ы
       Предопределены псевдонимы:
         - root: - корневая директория проекта;
         - url: - URL текущей ветки проекта. """
    logging.basicConfig(level = logging.INFO, \
                        stream = sys.stdout, \
                        format = '%(message)s')
    self.svn = sys.argv[1]
    self.aliases = None
    self.root = ''
    self.url_val = None
    list = [self.svn]
    if len(sys.argv) > 2:
      command = sys.argv[2]
      list.append(command)
      for arg in sys.argv[3:]:
        i = arg.find(':')
        log.debug('[%s].find(":")=%s', arg, i)
        if i > 0:
          val = self.alias(arg[:i])
          if val != None:
            suffix = arg[i + 1:]
            if suffix == '':
              arg = val
            else:
              arg = val + '/' + arg[i + 1:]
        list.append(arg)
      if command in ('cleanup', 'commit', 'ci', 'revert', 'status', 'st', 'up', 'update'):
        count = 1
      elif command in ('merge', 'sw', 'switch'):
        count = 2
      else:
        count = 0
      if count > 0 and self.alias('root') != '':
        for arg in list[2:]:
          if not arg.startswith('-'):
            count -= 1
        log.debug('count=%s', count)
        if count > 0:
          list.append(self.root)
    log.debug('%s', list)
    system(list)
  def alias(self, name):
    """ Возвращает значение из свойства svn pg aliases """
    if self.aliases == None:
      log.debug('alias(%s)', name)
      svn = '.svn'
      url = None
      while True:
        if not os.path.isdir(svn) \
		or (url != None and \
                not (url.startswith(self.url()) and self.url()[len(url)+1:].find('/') < 0)):
          self.root = ''
          self.url_val = None
          self.aliases = dict()
          log.debug('svn pg aliases: not found. Using root=%s', self.root)
          break
        url = self.url()
        system([self.svn, 'pg', 'aliases', self.root], self.read_alias)
        if len(self.aliases) > 0:
          log.debug('svn pg aliases: found. Using root=%s', self.root)
          break
        if self.root == '':
          self.root = '..'
        else:
          self.root = '../' + self.root
        log.debug('svn pg aliases: not found. Search from %s', self.root)
        svn = self.root + '/.svn'
        self.url_val = None
    if 'root' == name:
      return self.root
    if 'url' == name:
      return self.get_url()
    return self.aliases.get(name)
  def get_url(self):
    """ Возвращает URL """
    if self.url_val == None:
      self.url_val = self.url()
    return self.url_val
  def url(self):
    """ Возвращает URL """
    if self.url_val == None:
      command = [self.svn, 'info']
      if self.root != '':
        command.append(self.root)
      self.url_val = system(command, self.read_url)
      log.debug('URL: %s', self.url_val)
    return self.url_val
  def read_alias(self, stdout):
    """ Читает свойства в виде строк, псевдоним=url, из svn pg aliases """
    self.aliases = dict()
    pattern = re.compile(r'^\s*(\S+)\s*=\s*(.+)$')
    for line in stdout:
      m = pattern.match(line)
      if m == None:
        log.debug('pattern not matches: [%s]', line)
      else:
        self.aliases[m.group(1)] = m.group(2)
  def read_url(self, stdout):
    """ Читает URL из svn info """
    pattern = re.compile(r'^URL:\s*(\S+)\s*$')
    for line in stdout:
      m = pattern.match(line)
      if m != None:
        return m.group(1)
    log.error('URL not found')
    sys.exit()

if __name__ == '__main__':
  log = logging.getLogger('svn')
  Main()
