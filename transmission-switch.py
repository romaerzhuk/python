#!/usr/bin/python
import sys, transmissionrpc

def main():
  tc = transmissionrpc.Client('localhost', port=9091)
  ids = tc.list().keys()
  if len(sys.argv) > 1:
    command = sys.argv[1]
  else:
    command = None
  if "start" == command:
    tc.start(ids)
  elif "stop" == command:
    tc.stop(ids)
  else:
    print "usage:"
    print "\ttransmission-switch start|stop"

if __name__ == '__main__':
  main()
