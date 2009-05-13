#!/usr/bin/python
# -*- coding: utf8 -*-

import sys, os

class RemoveDeadHeads:
  def __init__(self, options, tmp):
    self.tmp = tmp
    self.system("bzr init-repo %1s %2s" % (options, tmp))
    self.clone('.')
    os.rename(".bzr", tmp + '/' + tmp)
    os.rename(tmp + "/.bzr", ".bzr")
    self.removedir(tmp)
  def clone(self, path):
    if ".bzr" == path or self.tmp == path or not os.path.isdir(path):
      return
    if ".bzr" == os.path.basename(path):
      print "clone(%1s)" % path
      path = os.path.dirname(path)
      mkdirs(self.tmp + '/' + os.path.dirname(path))
      self.system("bzr branch %1s %2s" % (path, self.tmp + '/' + path))
      return
    if path == '.': prefix = ''
    else: prefix = path + '/'
    for i in os.listdir(path):
      self.clone(prefix + i)
  def system(self, command):
    res = os.system(command)
    if res != 0:
      raise IOError("command '%1s': res=%2s" % (command, res))
  def removedir(self, path):
    for i in os.listdir(path):
      s = path + '/' + i
      if os.path.isfile(s):
        os.remove(s)
      else:
        self.removedir(s)
    os.rmdir(path)

# Создаёт вложенные директории.
# Если директории уже существуют, ничего не делает
def mkdirs(path):
  #print "mkdirs(" + path + ")"
  if os.path.exists(path):
    return
  mkdirs(os.path.dirname(path))
  os.mkdir(path)

if __name__ == "__main__":
  RemoveDeadHeads("--1.9-rich-root --no-tree", "bzr-repo.tmp")
