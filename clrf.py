#!/usr/bin/python
import sys, re, os

"""Replace CRLF with LF in argument files."""

def clrf(file):
  data = open(file, "rb").read()
  newdata = re.sub("\r\n", "\n", data)
  if newdata != data:
    f = open(file, "wb")
    f.write(newdata)
    f.close()

if __name__=='__main__':
  for file in sys.argv[1:]:
    clrf(file)
