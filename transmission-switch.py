#!/usr/bin/python
import sys, transmissionrpc

def main():
  tc = transmissionrpc.Client('localhost', port=9091)
  torrents = tc.list()
  ids = torrents.keys()
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
  removed=[]
  for t in torrents.values():
    if t.ratio >= 1.2:
      removed.append(t.id)
  if len(removed) > 0:
    tc.remove(removed)

if __name__ == '__main__':
  main()
