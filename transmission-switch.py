#!/usr/bin/python
import sys, datetime, transmissionrpc

def main():
  tc = transmissionrpc.Client('localhost', port=9091)
  fields = ['id', 'hashString', 'name', 'sizeWhenDone', 'leftUntilDone'
            , 'eta', 'status', 'rateUpload', 'rateDownload', 'uploadedEver'
            , 'downloadedEver', 'doneDate']
  torrents = tc._request('torrent-get', {'fields': fields})
  #torrents = tc.list()
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
  max_date = datetime.datetime.today() - datetime.timedelta(92)
  #print "max_date=", max_date
  removed=[]
  for t in torrents.values():
    if t.ratio >= 1.2 or t.progress >= 100 and t.date_done < max_date:
      #print t.id, t.hashString, t.date_done, t.progress, t.ratio, t.name
      removed.append([t.id, t.hashString])
  #print removed
  if len(removed) > 0:
    tc.remove(removed)

if __name__ == '__main__':
  main()
