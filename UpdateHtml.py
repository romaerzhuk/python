# -*- coding: cp1251 -*-
import sys, re, dir, FileFilter

class Updater:
  """
  Ищет в файле нужную строку и заменяет на новую
  Для вложенных директорий новая строка дополняется спереди ../
  """
  def __init__(self,path,old,new):
    if path=='.': self.prefix=''
    else: self.prefix=path+'/'
    self.old,self.new=old,new
  def __call__(self, file):
    assert(file[0:len(self.prefix)]==self.prefix)
    deep='../'*file[len(self.prefix):].count('/')
    r = open(file, "r")
    data = r.read()
    r.close()
    newdata = data.replace(self.old, deep+self.new)
    if newdata != data:
      #print "file='%s' prefix='%s'deep='%s'"%(file,self.prefix,deep)
      f = open(file, "w")
      f.write(newdata)
      f.close()

if __name__=='__main__':
  if len(sys.argv)<4:
    print "usage: ", sys.argv[0], "<dir> <searchString> <replaceString>"
  else:
    path=sys.argv[1]
    dir.through_files(path, Updater(path,sys.argv[2],sys.argv[3]), \
      FileFilter.Filter(["*.htm", "*.html"]))
