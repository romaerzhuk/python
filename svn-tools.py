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

def switch(url):
  system(["svn", "switch", url]) 

def update():
  system(["svn", "update"])

def merge(url):
  system(["svn", "merge", url])

class Main:
  def __init__(self):
    """ Выполняет команду svn-tools """
    logging.basicConfig(level = logging.INFO, \
                        stream = sys.stdout, \
                        format = "%(message)s")
    self.props = ".svn/branch"
    if not os.path.isfile(self.props):
      log.error("File [%s] not found", self.props)
      self.help()
    command = self.arg(1, "command")
    pattern = re.compile(r"^\s*(\S+)\s*=\s*(.+)$")
    self.values = dict()
    with open(self.props, "r") as fd:
      for line in fd:
        m = pattern.match(line)
        if m == None:
          log.debug("pattern not matches: [%s]", line) 
        else:
          self.values[m.group(1)] = m.group(2)
          log.debug("values[%s]=[%s]", m.group(1), m.group(2))
    log.debug("test command [%s]", command)
    if "switch-branch" == command:
      switch(self.branch())
    elif "switch-trunk" == command:
      switch(self.trunk())
    elif "reintegrate" == command:
      switch(self.trunk())
      system(["svn", "merge", "--reintegrate", self.branch()]) 
      pass
    elif "merge" == command:
      switch(self.branch())
      merge(self.trunk())
    elif "rebase" == command:
      switch(self.branch())
      merge(self.trunk())
      system(["svn", "resolve", "--accept", "working", "--recursive", "."])
    elif "tag" == command:
      system(["svn", "copy", "--message", \
        self.arg(2, "message"), ".", self.tags() + '/' + self.arg(3, "tag_name")])
    else:
      log.error("Unknown command [%s]", command)
      self.help()
  def help(self):
    """ Выводит справку об использовании """
    print "Usage: svn-tools.py command"
    print "\ncommands:"
    print "\tswitch-branch          -- svn switch to branch"
    print "\tswitch-trunk           -- svn switch to trunk"
    print "\treintegrate            -- svn merge --reintegrate branch into trunk"
    print "\tmerge                  -- svn merge trunk into branch"
    print "\trebase                 -- svn switch to branch and restore after reintegrate"
    print "\ttag message tag_name   -- svn copy -m message . tags/tag_name"
    print "\nsvn-tools used the file '%s' with properties:" % self.props
    print " trunk  = URL_TO_TRUNK"
    print " branch = URL_TO_BRANCH"
    print " tags   = URL_TO_TAGS"
    sys.exit()
  def arg(self, index, name):
    """ Возвращает аргумент из командной строки """
    if len(sys.argv) < index:
      log.error("The %s argument expected", name)
      self.help()
    return sys.argv[index]
  def value(self, name):
    """ Возвращает значение из файла .svn/branch """
    val = self.values.get(name)
    if val == None:
      log.error("Property [%s] not found in %s", name, self.props)
      self.help()
    return val
  def trunk(self):
    return self.value("trunk")
  def branch(self):
    return self.value("branch")
  def tags(self):
    return self.value("tags")

if __name__ == '__main__':
  log = logging.getLogger("svn.tools")
  Main()
