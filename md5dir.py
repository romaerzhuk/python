#!/usr/bin/python
import sys, os, md5
import dir

def md5dir(path):
  print "md5dir(%s)" % path
  suffix = ".md5"
  for i in os.listdir(path):
    file = path + '/' + i 
    print "file=%s" % file
    if not os.path.isdir(file) and not i.endswith(suffix):
      print "create md5 for %s" % file
      sum = md5.new()
      fd  = open(file, "rb")
      while 1:
        buf = fd.read(8192)
        if len(buf) == 0:
          break
        sum.update(buf)
      fd.close()
      fd = open(file+suffix, "w")
      fd.write("%s\t*%s\n" % (sum.hexdigest(), i))

if __name__=='__main__':
  if len(sys.argv) < 2:
    dir.through_dirs('.', md5dir) 
  else:
    for path in sys.argv[1:]:
      dir.through_dirs(path, md5dir) 
