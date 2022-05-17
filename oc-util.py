#!/usr/bin/python3

import logging as log
import re
import subprocess
import sys
import yaml

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


def main():
    log.basicConfig(level='INFO', stream=sys.stdout, format="%(levelname)5s %(lineno)3d %(message)s")
    projects = ['ds5-genr02-dbor-sck4-test1',
                'ds5-genr02-dbor-sck4-dev',
                'ds5-genr02-dbor-sck-demo',
                'ds5-genr02-dbor-sck-dev',
                'ds5-genr02-dbor-sck-test',
                'ds5-genr02-dbor-sck-test2']
    #for project in projects:
    ##    system(['oc', 'project', project])
    deployments = system(['oc', 'get', 'deploy', '--output=yaml'], reader=yaml.safe_load)
    for item in deployments['items']:
        metadata = item['metadata']
        labels = metadata['labels']
        status = item['status']
        if labels.get('version') == None:
            print(item)
            sys.exit(1)
        print('%s\t%s' % (metadata['name'], labels['version']))

if __name__ == '__main__':
    main()
