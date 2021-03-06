#!/usr/bin/python
import sys, datetime, transmissionrpc

def main():
  tc = transmissionrpc.Client('localhost', port=9091)
  torrents = tc.info()
  ids = torrents.keys()
  if len(sys.argv) > 1:
    command = sys.argv[1]
  else:
    command = None
  if ids == None or len(ids) == 0:
    return
  if "start" == command:
    tc.start(ids)
  elif "stop" == command:
    tc.stop(ids)
  elif "check" != command:
    print "usage:"
    print "\ttransmission-switch start|stop|check"
  max_date = datetime.datetime.today() - datetime.timedelta(30)
  #print "max_date=", max_date
  removed=[]
  for t in torrents.values():
    #print t.id, t.hashString, t.date_done, t.progress, t.ratio, t.name
    if t.ratio >= 30 or t.progress >= 100 and t.date_done < max_date:
      removed.append(t.id)
  #print removed
  if len(removed) > 0:
    tc.remove(removed)

if __name__ == '__main__':
  main()
