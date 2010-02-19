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

def help():
  """ Выводит справку об использовании """
  print "Usage: svn-tools.py command"
  print "\ncommands:"
  print "\tswitch-branch -- svn switch to branch"
  print "\tswitch-trunk  -- svn switch to trunk"
  print "\treintegrate   -- svn merge --reintegrate branch into trunk"
  print "\tmerge         -- svn merge trunk into branch"
  print "\trebase        -- svn switch to branch and restore after reintegrate"
  print "\nsvn-tools used the file 'svn-branch' with contents:"
  print " trunk  = URL_TO_TRUNK"
  print " branch = URL_TO_BRANCH"
  sys.exit()

def switch(url):
  system(["svn", "switch", url]) 

def update():
  system(["svn", "update"])

def merge(url):
  system(["svn", "merge", url])

def read_url(lines):
  prefix = "URL: "
  for line in lines:
    if (line.startswith(prefix)):
      return line[len(prefix):].rstrip()

def assert_url(url):
  info = system(["svn", "info"], read_url)
  log.debug("svn url=[%s]", info)
  if info != url:
    log.error("expected [%s], but was [%s]", url, info)
    sys.exit(1)

def main():
  """ Выполняет команду svn-tools """
  logging.basicConfig(level = logging.INFO, \
                      stream = sys.stdout, \
                      format = "%(message)s")
  if len(sys.argv) < 1:
    help()
  svn_branch = "svn-branch"
  if not os.path.isfile(svn_branch):
    log.error("File [%s] not found", svn_branch)
    help()
  command = sys.argv[1]
  pattern = re.compile(r"^\s*(\S+)\s*=\s*(.+)$")
  trunk, branch = (None, None)
  with open(svn_branch, "r") as fd:
    for line in fd:
      m = pattern.match(line)
      if m == None:
        log.debug("pattern not matches: [%s]", line) 
      else:
        name, value = (m.group(1), m.group(2))
        if "trunk" == name:
          trunk = value 
          log.debug("trunk=[%s]", value)
        elif "branch" == name:
          branch = value
          log.debug("branch=[%s]", value)
        else:
          log.debug("unknown property [%s]", name)
  if trunk == None:
    log.error("Property [trunk] undefined")
    help()
  if branch == None:
    log.error("Property [branch] undefined")
    help()
  log.debug("test command [%s]", command)
  if "switch-branch" == command:
    switch(branch)
  elif "switch-trunk" == command:
    switch(trunk)
  elif "reintegrate" == command:
    assert_url(trunk)
    update()
    system(["svn", "merge", "--reintegrate", branch]) 
    pass
  elif "merge" == command:
    assert_url(branch)
    update()
    merge(trunk)
  elif "rebase" == command:
    switch(branch)
    merge(trunk)
    system(["svn", "resolve", "--accept", "working"])
  else:
    log.error("Unknown command [%s]", command)
    help()

if __name__ == '__main__':
  log = logging.getLogger("backup")
  main()
