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

def tunfilter(stdout):
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
    return list

def main():
    log.basicConfig(level='INFO', stream=sys.stdout, format="%(levelname)5s %(lineno)3d %(message)s")
    list = system(['route', '-n'], tunfilter)
    log.debug('%s', list)
    for s in list:
        system(['route', 'del', '-net', s[0], 'netmask', s[1]])

if __name__ == '__main__':
    main()
