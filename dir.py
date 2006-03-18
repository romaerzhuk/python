import os, dospath, sys

def through_files(path,proc=None,fileFilter=None):
  if path=='.': prefix=''
  else: prefix=path+'/'
  for i in os.listdir(path):
    s=prefix+i
    if dospath.isdir(s):
      through_files(s,proc,fileFilter)
    else:
      if fileFilter==None or fileFilter(s):
        if proc==None:
          print s
        else:
          proc(s)

def through_dirs(path,proc=None,fileFilter=None):
  if path=='.': prefix=''
  else: prefix=path+'/'
  if fileFilter==None or fileFilter(path):
    if proc==None:
      print path
    else:
      proc(path)
  for i in os.listdir(path):
    s=prefix+i
    if dospath.isdir(s):
      through_dirs(s,proc,fileFilter)

if __name__=='__main__':
  if len(sys.argv)<2:
    lst=through_files('.')
  else:
    lst=through_files(sys.argv[1])
