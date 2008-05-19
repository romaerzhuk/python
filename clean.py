# -*- coding: cp1251 -*-
import sys, os, string, FileFilter, dir

def clean(path):
  work=os.environ['HOMEDRIVE']+os.environ['HOMEPATH']+'\work'
  path=os.path.abspath(path)
  if string.find(path, work) < 0:
    print "work directory is", work
    print '"%1s" is not work directory ' % (path)
  else:
    dir.through_files(path, os.remove, FileFilter.Filter(work+'/дом/cleaned'))

if __name__=='__main__':
  clean(sys.argv[1])
