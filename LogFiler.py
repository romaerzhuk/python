# -*- coding: cp1251 -*-

import os, re, FileFilter, ListFile

if __name__=='__main__':
  path='log'
  logLevel='INFO'
  logCode='0'
  strSearch='\d+'
  reStr='^(\d\d\.\d\d\.\d\d\d\d \d\d:\d\d:\d\d)\.\d\d\d: ' \
  	+logLevel+'[ ]*:[ ]*'+logCode \
  	+':.*длина=(\d+\.?\d*) м.*\{1, ([+-]?\d*\.?\d+) см\}, \{1, ([+-]?\d*\.?\d+) см\}\]$'
  reVal=re.compile(reStr)
  logFile=FileFilter.Filter(['*.log'])
  logList=[]
  for file in os.listdir(path):
    if not os.path.isdir(file) and logFile(file):
      logList.append(path+'/'+file)
  logList.sort()
  for file in logList:
      for line in ListFile.List(file):
        m=reVal.search(line)
        if m != None and m.group(2) > 15:
          print m.group(1), m.group(2), m.group(3), m.group(4)

