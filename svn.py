#!/usr/bin/python
# -*- coding: utf8 -*-
from __future__ import with_statement
import sys, os, re, platform, logging, subprocess

def system(command, reader = None, stdin = None, cwd = None):
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

class Main:
  def __init__(self):
    """ Выполняет команду svn с заменой trunk:, branch:, tag:  на соответствующие URL-ы
       Так же определены псевдонимы:
         - корневая директория проекта - root:
         - URL текущей ветки проекта - url:
        """
    logging.basicConfig(level = logging.INFO, \
                        stream = sys.stdout, \
                        format = "%(message)s")
    self.props = 'url'
    self.svn = sys.argv[1]
    self.aliases = None
    self.url_val = None
    self.dir = ''
    list = [self.svn]
    for arg in sys.argv[2:]:
      i = arg.find(':')
      log.debug('[%s].find(":")=%s', arg, i)
      if i > 0:
        val = self.alias(arg[:i])
        if val != None:
          arg = val + '/' + arg[i + 1:]
      list.append(arg)
    log.debug('%s', list)
    system(list)
  def alias(self, name):
    """ Возвращает значение из файла .svn/url """
    if self.aliases == None:
      log.debug("alias(%s)", name)
      props = self.dir + '.svn/' + self.props
      while not os.path.isfile(props):
        self.dir = '../' + self.dir
        log.debug('%s not found, search from %s', props, dir)
        if not os.path.isdir(self.dir):
          log.error('File [.svn/%s] not found', self.props)
          sys.exit()
        props = self.dir + '.svn/' + self.props
      self.aliases = dict()
      pattern = re.compile(r'^\s*(\S+)\s*=\s*(.+)$')
      with open(props, "r") as fd:
        for line in fd:
          log.debug("line: [%s]", line)
          m = pattern.match(line)
          if m == None:
            log.debug("pattern not matches: [%s]", line)
          else:
            self.aliases[m.group(1)] = m.group(2)
    if 'root' == name:
      return self.dir
    if 'url' == name:
      return self.url()
    return self.aliases.get(name)
  def url(self):
    """ Возвращает URL """
    if self.url_val == None:
      command = [self.svn, 'info']
      if self.dir != '':
        command.append(self.dir)
      self.url_val = system(command, self.read_url)
      log.debug("URL: %s", self.url_val)
    return self.url_val
  def read_url(self, stdout):
    """ Читает URL из svn info """
    if self.url_val == None:
      pattern = re.compile(r'^URL:[ ]*(.+)$')
      for line in stdout:
        m = pattern.match(line)
        if m != None:
          return m.group(1)
      log.error("URL not found")
      sys.exit()

if __name__ == '__main__':
  log = logging.getLogger("svn")
  Main()
