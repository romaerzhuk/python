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
    """ Выполняет команду svn с заменой trunk:, branch:, tag: на соответствующие URL-ы """
    logging.basicConfig(level = logging.INFO, \
                        stream = sys.stdout, \
                        format = "%(message)s")
    self.props = '.svn/url'
    self.aliases = None
    self.url_val = None
    list = [sys.argv[1]]
    for arg in sys.argv[2:]:
      i = arg.find(':')
      if i > 0:
        val = self.alias(arg[:i])
        if val != None:
          arg = val + '/' + arg[i + 1:]
      list.append(arg)
    log.debug('%s', list)
    system(list)
  def alias(self, name):
    """ Возвращает значение из файла .svn/url """
    if 'url' == name:
      return self.url()
    if self.aliases == None:
      self.aliases = dict()
      log.debug("alias(%s)", name)
      pattern = re.compile(r'^\s*(\S+)\s*=\s*(.+)$')
      if not os.path.isfile(self.props):
        log.error("File [%s] not found", self.props)
        sys.exit()
      with open(self.props, "r") as fd:
        for line in fd:
          log.debug("line: [%s]", line)
          m = pattern.match(line)
          if m == None:
            log.debug("pattern not matches: [%s]", line)
          else:
            self.aliases[m.group(1)] = m.group(2)
    return self.aliases.get(name)
  def url(self):
    """ Возвращает URL """
    if self.url_val == None:
      self.url_val = system(["svn", "info"], self.read_url)
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
      self.help()

if __name__ == '__main__':
  log = logging.getLogger("svn.tools")
  Main()
