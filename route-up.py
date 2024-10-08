#!/usr/bin/python3

import logging as log
import re
import subprocess
import sys

def system(command, reader=None, stdin=None, cwd=None):
    """ Запускает процесс.
    Вызывает процедуру для чтения стандартного вывода.
    Возвращает результат процедуры """
    log.debug('%s', command)
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=stdin, cwd=cwd)
    if reader is None:
        for line in p.stdout:
            print(line.rstrip())
        return p.wait()
    res = reader(p.stdout)
    # дочитывает стандартный вывод, если что-то осталось
    for _ in p.stdout:
        pass
    p.wait()
    return res

def tunsnx(stdout):
    pattern = re.compile(r'^(\S+)\s+(\S+)\s+(\S+)\s+.*\stunsnx$')
    includes = re.compile(r'^(10.187.)|(10.189.)|(217.)')
    excludes = re.compile(r'^(217.0.0.0)|(217.8.0.0)|(217.32.0.0)|(217.64.0.0)|(217.128.0.0)')
    list = []
    for line in stdout:
        line = line.rstrip().decode('utf-8')
        m = pattern.match(line)
        match = m is not None
        exclude = match and excludes.match(m.group(1)) is not None
        include = match and includes.match(m.group(1)) is not None
        log.debug('%s -> match=%s, exclude=%s, include=%s', line, match, exclude, include)
        if match and (exclude or not include):
            list.append((m.group(1), m.group(3)))
    log.debug('%s', list)
    if not list:
        return
    for s in list:
        system(['route', 'del', '-net', s[0], 'netmask', s[1]])
    # DNS: 10.230.192.77 10.230.192.78
    #system(['route', 'add', '-net', '10.230.192.76', 'netmask', '255.255.255.252', 'dev', 'tunsnx'])
    # mskxdag.region.vtb.ru 10.132.168.204
    #system(['route', 'add', '-net', '10.132.168.204', 'netmask', '255.255.255.255', 'dev', 'tunsnx'])
    # vdi.vtb.ru 10.184.194.178
    #system(['route', 'add', '-net', '10.184.194.178', 'netmask', '255.255.255.255', 'dev', 'tunsnx'])
    system(['route', 'add', '-net', '10.0.0.0', 'netmask', '255.0.0.0', 'dev', 'tunsnx'])

def cscotun(stdout):
    pattern = re.compile(r'^(\S+)\s+(\S+)\s+(\S+)\s+.*\scscotun0$')
    excludes = re.compile(r'^(172\.)')
    list = []
    for line in stdout:
        line = line.rstrip().decode('utf-8')
        m = pattern.match(line)
        match = m is not None
        exclude = match and excludes.match(m.group(1)) is not None
        log.debug('%s -> match=%s, exclude=%s', line, match, exclude)
        if match and exclude:
            list.append((m.group(1), m.group(3)))
    log.debug('%s', list)
    if not list:
        return
    for s in list:
        system(['route', 'del', '-net', s[0], 'netmask', s[1]])
    system(['route', 'add', '-net', '172.17.0.0', 'netmask', '255.255.0.0', 'dev', 'docker0'])
    system(['route', 'add', '-net', '172.18.0.0', 'netmask', '255.255.0.0', 'dev', 'br-ca4dc9d07252'])
    system(['route', 'add', '-net', '172.19.0.0', 'netmask', '255.255.0.0', 'dev', 'br-df708bb8247e'])
#172.17.0.0      0.0.0.0         255.255.0.0     U     0      0        0 docker0
#172.18.0.0      0.0.0.0         255.255.0.0     U     0      0        0 cscotun0
#172.18.0.0      0.0.0.0         255.255.0.0     U     0      0        0 br-ca4dc9d07252
#172.19.0.0      0.0.0.0         255.255.0.0     U     0      0        0 cscotun0
#172.19.0.0      0.0.0.0         255.255.0.0     U     0      0        0 br-df708bb8247e

def main():
    log.basicConfig(level='INFO', stream=sys.stdout, format="%(levelname)5s %(lineno)3d %(message)s")
    system(['route', '-n'], tunsnx)
    #system(['route', '-n'], cscotun)

if __name__ == '__main__':
    main()
