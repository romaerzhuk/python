import xreadlines, os, string,sys, codecs, StringIO

"""
Читает ввод и выполняет системную команду с параметром-строкой
"""
def xarg(com, input):
  while 1:
    s=input.readline()
    if s=='': break
    os.system(com + ' "' + s.strip() + '"')
  
if __name__=='__main__':
  # Have stdin translate cp866 input into cp1251 input
  sys.stdin = codecs.EncodedFile(sys.stdin, 'cp1251', 'cp866')
  xarg(sys.argv[1], sys.stdin)