import os, dospath, re, FileFilter, ListFile

if __name__=='__main__':
  path='log'
  logLevel='WARN'
  logCode='24'
  strSearch='\d+'
  reStr='^(\d\d\.\d\d\.\d\d\d\d \d\d:\d\d:\d\d\.\d\d\d): '+logLevel+'[ ]*:[ ]*'+logCode+':.*-(\d*)$'
  reVal=re.compile(reStr)
  logFile=FileFilter.Filter(['*.log'])
  logList=[]
  for file in os.listdir(path):
    if not dospath.isdir(file) and logFile(file):
      logList.append(path+'/'+file)
  logList.sort()
  for file in logList:
      for line in ListFile.List(file):
        m=reVal.search(line)
        if m != None:
          print m.group(1), m.group(2)

