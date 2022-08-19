#!/usr/bin/python3
# -*- coding: utf8 -*-

from __future__ import with_statement

import atexit
import functools
import hashlib
import json
import logging as log
import os
import platform
import re
import smtplib
import socket
import subprocess
import sys
import time
import traceback
from email.mime.text import MIMEText
from typing import Tuple, Dict, Optional, List, Set, AnyStr, Match, Callable, BinaryIO, Pattern, Iterable, Any, IO, \
    Sequence


def through_dirs(path: str, dir_filter: Callable[[str], bool], func: Callable[[str], Any] = None) -> None:
    """ Рекурсивно сканирует директории.
    Вызывает для каждой директории фильтр. """
    if dir_filter(path):
        return
    if path == '.':
        prefix = ''
    else:
        prefix = path + '/'
    for i in os.listdir(path):
        s = prefix + i
        if os.path.isdir(os.path.realpath(s)):
            through_dirs(s, dir_filter, func)
        elif func is not None:
            func(s)


class StopWatch:
    """ Засекает время выполнения команды """

    def __init__(self, msg: Any):
        self.msg = msg
        self.start = time.time()

    def stop(self) -> None:
        log.info("[%s]: %1.3f sec", self.msg, time.time() - self.start)


def stop_watch(msg, func: Callable[[], Any]) -> Any:
    """ Засекает время выполнения команды """
    start = time.time()
    result = func()
    log.info("[%s]: %1.3f sec", msg, time.time() - start)
    return result


def md5sum(path: Optional[str],
           input_stream: IO = None, out: IO = None,
           is_stop_watch: bool = True,
           multiplier: Callable[[], int] = None) -> Any:
    """ Вычисляет контрольную сумму файла в шестнадцатеричном виде """

    def md5_by_path():
        return with_open(path, 'rb', lambda f: md5sum(path, f, out=out, multiplier=multiplier))

    if input_stream is None:
        if not os.path.isfile(path):
            return None
        return stop_watch('md5sum -b %s' % path, md5_by_path) if is_stop_watch else md5_by_path()

    checksum = hashlib.md5()
    while True:
        n = multiplier() if multiplier is not None else 1024
        buf = input_stream.read(1024 * n)
        if len(buf) == 0:
            return checksum.hexdigest().lower()
        checksum.update(buf)
        if out is not None:
            out.write(buf)


class GzipMd5sum:
    """ Сжимает поток, считает контрольную сумму сжатого потока, и пишет в файл """

    def __init__(self, path: str):
        self.path = path

    def __call__(self, input_stream: IO):
        with open(self.path, "wb") as out:
            return system_hidden(["gzip"], lambda stdout: md5sum(None, stdout, out), input_stream)


def write_md5(file: IO, checksum: str, name: str) -> None:
    """  Пишет в открытый файл контрольную сумму
    file - открытый файл
    md5sum - сумма, в 16-ричном виде
    name - имя файла
    """
    file.write(bytes("%s\t*%s\n" % (checksum, name), 'UTF-8'))


def load_md5(path: str) -> Dict[str, str]:
    """ Возвращает множество контрольных сумм из файла """
    pattern = re.compile(r"^(\S+)\s+\*(.+)$")
    lines = dict()
    if os.path.isfile(path):
        with open(path, encoding='UTF-8') as fd:
            for line in fd:
                m = pattern.match(line)
                if m is not None:
                    lines[m.group(2)] = m.group(1).lower()
    return lines


def load_md5_with_times(path: str) -> Dict[str, Tuple[str, float]]:
    """ Возвращает dict множество контрольных сумм md5 из файла и время подсчёта md5 каждого файла """
    if not os.path.isfile(path):
        return {}

    def read(fd) -> Dict[str, Tuple[str, float]]:
        pattern = re.compile(r'^(\S+)\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+[+-]\d\d:\d\d)\s+(.+)$')
        result = {}
        for line in fd:
            m = pattern.match(line)
            if m is not None:
                try:
                    t = time_from_string(m.group(2))
                    result[m.group(3)] = (m.group(1).lower(), t)
                except ValueError:
                    pass
        return result

    return with_open(path, 'r', read)


def mkdirs(path):
    """  Создаёт вложенные директории.
    Если директории уже существуют, ничего не делает """
    log.debug("mkdirs(%s)", path)
    if os.path.exists(path):
        return
    mkdirs(os.path.dirname(path))
    if not os.path.exists(path):
        os.mkdir(path)


def read_line(file):
    """ Возвращает первую строку из файла """
    with open(file, encoding='UTF-8') as fd:
        return fd.readline()


def with_open(path: str, mode: str, handler: Callable[[IO], Any]) -> Any:
    """ Открывает файл и передаёт управление в handler """
    with open(path, mode, encoding=None if 'b' in mode else 'UTF-8') as f:
        return handler(f)


def dir_contains(directory, dirs, files):
    """ Проверяет наличие в директории списка директорий и файлов """
    for name in dirs:
        path = directory + '/' + name
        if not os.path.isdir(path):
            return False
    for name in files:
        path = directory + '/' + name
        if not os.path.isfile(path):
            return False
    return True


def remove_file(path: str) -> None:
    """ Удаляет файл, если он существует """
    if os.path.isfile(path):
        os.remove(path)


def system(command: Sequence[str], reader: Callable[[IO], Any] = None, stdin: IO = None, cwd: str = None):
    """ Запускает процесс.
    Вызывает процедуру для чтения стандартного вывода.
    Возвращает результат процедуры.
    Выводит на экран команду
     """
    sw = StopWatch(' '.join(command))
    res = system_hidden(command, reader, stdin, cwd)
    sw.stop()
    return res


def system_hidden(command: Sequence[str],
                  reader: Callable[[IO], Any] = None,
                  stdin: IO = None,
                  cwd: str = None) -> Any:
    """ Запускает процесс.
    Вызывает процедуру для чтения стандартного вывода.
    Возвращает результат процедуры """
    try:
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=stdin, cwd=cwd)
    except Exception as e:
        if platform.system() != "Windows":
            raise e
        p = subprocess.Popen(["cmd.exe", "/c"] + list(command), stdout=subprocess.PIPE, stdin=stdin, cwd=cwd)
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


class RecoveryEntry:
    """ Файл, подготовленный к восстановлению """

    def __init__(self, name: str) -> None:
        self.name: str = name  # путь файла без префикса резервной директории
        self.md5: Dict[str, str] = dict()  # контрольная сумма файла в соответствущей директории
        self.dir: Optional[str] = None  # имя директории с корректным файлом
        self.list: List[str] = []  # список директорий, куда нужно восстанавливать файл

    def __repr__(self) -> str:
        return "Entry(name=%s, dir=%s, list=%s)" % (self.name, self.dir, self.list)


class Separator:
    """ Отделяет нужные резервные копии от избыточных """

    def __init__(self, pattern: str):
        self.pattern: Pattern[AnyStr] = re.compile(pattern)

    @staticmethod
    def init(entry: RecoveryEntry, matcher: Optional[Match[AnyStr]]):
        """ Инициализирует Entry """
        pass

    def separate(self, entry_list: List[RecoveryEntry]) -> Tuple[List[RecoveryEntry], List[RecoveryEntry]]:
        """ Отделяет нужные резервные копии от избыточных """
        pass


class TimeSeparator(Separator):
    """ Отделяет нужные копии от избыточных по дате создания """

    def __init__(self, num: int):
        super().__init__(r"^.+(\d\d\d\d-\d\d-\d\d)\..+$")
        self.num = num

    @staticmethod
    def init(entry: RecoveryEntry, matcher: Optional[Match[str]]):
        """ Инициализирует Entry """
        entry.date = matcher.group(1)

    def separate(self, entry_list: List[RecoveryEntry]):
        """ Сортирует список по времени в обратном порядке, оставляет первые self.num элементов """
        entry_list.sort(key=functools.cmp_to_key(self.cmp))
        return entry_list[:self.num], entry_list[self.num:]

    @staticmethod
    def cmp(e1: RecoveryEntry, e2: RecoveryEntry) -> int:
        """ Сравнивает файлы по дате: e1.date <= e2.date """
        if e1.dir is not None:
            if e2.dir is None:
                return - 1
        elif e2.dir is not None:
            return 1
        # noinspection PyUnresolvedReferences
        return ((e1.date <= e2.date) << 1) - 1


class SvnSeparator(Separator):
    """ Отделяет ненужные копии с перекрывающимися диапазонами ревизий svn """

    def __init__(self):
        super().__init__(r"^(.+)\.(\d+)-(\d+)\.svndmp\.gz$")

    @staticmethod
    def init(entry: RecoveryEntry, matcher: Optional[Match[str]]):
        """ Инициализирует Entry """
        entry.recovery = True
        entry.start = int(matcher.group(2))
        entry.stop = int(matcher.group(3))

    # noinspection PyUnresolvedReferences
    def separate(self, entry_list: List[RecoveryEntry]):
        """ Разделяет перекрывающиеся диапазоны ревизий """
        entry_list.sort(key=functools.cmp_to_key(self.cmp))
        recovery, remove = [], []
        for i in range(len(entry_list)):
            ei = entry_list[i]
            if ei.recovery:
                recovery.append(ei)
                if ei.dir is not None:
                    for j in range(i + 1, len(entry_list)):
                        ej = entry_list[j]
                        if ej.recovery and ei.stop >= ej.stop:
                            ej.recovery = False
                            remove.append(ej)
                        elif ei.stop < ej.start:
                            break
        return recovery, remove

    # noinspection PyUnresolvedReferences
    @staticmethod
    def cmp(e1: RecoveryEntry, e2: RecoveryEntry) -> int:
        """ Сортирует по ревизиям """
        cmp = e1.start - e2.start
        if cmp != 0:
            return cmp
        return e2.stop - e1.stop


class BackupStrategy:
    """ Стратегия снятия резервной копии """

    @staticmethod
    def found(directory: str) -> bool:
        """ Проверяет, что директория - подходит для снятия резервной стратегией """
        pass

    def backup(self, src: str, dst: str, prefix: str) -> bool:
        """ Снимает резервную копию для одиночного репозитория. Возвращает True, если была снята копия """
        pass


class SvnBackup(BackupStrategy):
    """ Запускает svnadmin dump для репозиториев Subversion
    Сохраняет в self.md5sums подсчитанные контрольные суммы """

    def __init__(self, backup):
        self.md5sums = backup.new_checksum_by_path

    @staticmethod
    def found(directory):
        """ Проверяет, что директория - репозиторий Subversion """
        if not dir_contains(directory, ['conf', 'db', 'hooks', 'locks'], ['format', 'README.txt']):
            return False
        if not read_line(directory + "/README.txt").startswith("This is a Subversion repository;"):
            return False
        return True

    def backup(self, src, dst, prefix):
        """ Снимает резервную копию для одиночного репозитория """
        if dst is None:
            log.debug("backup(src=%s, dst=%s, prefix=%s): ignore dst=[%s]", src, dst, prefix, dst)
            return
        mkdirs(dst)
        log.debug("backup(src=%s, dst=%s, prefix=%s)", src, dst, prefix)
        new_rev = self.svn_revision(src)
        md5 = load_md5(dst + "/.md5")
        step = min_rev = 100
        while new_rev >= step - 1 and step < 10000:
            step *= 10
        old_rev = -1
        while True:
            while old_rev + step > new_rev:
                step /= 10
            if step < min_rev:
                break
            rev = old_rev + step
            self.dump(src, dst, prefix, old_rev, rev, md5)
            old_rev = rev
        self.dump(src, dst, prefix, old_rev, new_rev, md5)
        return True

    def svn_revision(self, src):
        """  Возвращает ревизию репозитория """
        return system(("svn", "info", "file://" + os.path.abspath(src)), self.read_revision)

    def dump(self, src, dst, prefix, old_rev, new_rev, md5):
        """ Запускает svnadmin dump для одиночного репозитория """
        old_rev += 1
        log.debug("svn_dump(%s, %s, %s)", prefix, old_rev, new_rev)
        if old_rev > new_rev:
            return
        dump_name = "%s.%06d-%06d.svndmp.gz" % (prefix, old_rev, new_rev)
        path = dst + '/' + dump_name
        checksum = md5.get(dump_name)
        if checksum is not None and checksum == md5sum(path):
            self.md5sums[path] = checksum
            return
        self.md5sums[path] = system(["svnadmin", "dump", "-r",
                                     "%d:%d" % (old_rev, new_rev), "--incremental", src],
                                    GzipMd5sum(path))

    @staticmethod
    def read_revision(stdout):
        """ Читает номер ревизии Subversion из стандартного вывода """
        prefix = b"Revision: "
        for line in stdout:
            if line.startswith(prefix):
                return int(line[len(prefix):])
        raise IOError("Invalid subversion info")


class GitBackup(BackupStrategy):
    """ Создаёт резервную копию репозитория Git """

    def __init__(self, backup):
        self.last_modified = backup.last_modified
        self.up_to_date = backup.up_to_date
        self.generic_backup = backup.generic_backup
        self.excludes = {}

    @staticmethod
    def found(src):
        """ Проверяет, что директория - репозиторий Git """
        found = dir_contains(src, ['.git'], [])
        git = src
        if found:
            src += '/.git'
        else:
            found = dir_contains(src,
                                 ['branches', 'hooks', 'objects', 'refs'],
                                 ['config', 'HEAD'])
        if not found:
            return False
        log.info("git found: %s", git)
        config = src + '/config'
        log.debug("config=[%s]", config)
        return True

    def backup(self, src, dst, prefix):
        """ Создаёт резервную копию репозитория Git """
        if dir_contains(src, ['.git'], []):
            git = src + '/.git'
        else:
            git = src
        log.info("\nbackup git: %s", git)
        remotes = system_hidden(['git', 'config', '--list'], cwd=src, reader=self.read_remotes)
        for name in remotes['svn-remote']:
            system(['git', 'svn', 'fetch', name], cwd=src)
        mirrors = []
        for name in remotes['remote']:
            remote = remotes['remote'][name]
            mirror = remote.get('mirror')
            log.debug('remote.%s.mirror=%s', name, mirror)
            if mirror != 'true':
                system(['git', 'fetch', '--prune', name], cwd=src)
            else:
                mirrors.append(name)
        if len(mirrors) > 0:
            self.git_fsck(src)
            for name in mirrors:
                system(['git', 'push', name], cwd=src)
        self.excludes = {git + '/svn', git + '/FETCH_HEAD', git + '/subgit', git + '/refs/svn/map'}
        through_dirs(src, self.last_modified_with_excludes, self.last_modified_with_excludes)
        if self.up_to_date(src, dst):
            return
        system(['git', 'prune'], cwd=src)
        if len(mirrors) == 0:
            self.git_fsck(src)
        self.generic_backup(src, dst, prefix)

    @staticmethod
    def git_fsck(src):
        """ Проверяет целостность репоизитория Git """
        res = system(['git', 'fsck', '--full', '--strict', '--no-progress'], cwd=src)
        if res != 0:
            raise IOError('Invalid git repository %s' % src)

    def last_modified_with_excludes(self, path):
        """ Запоминает время последней модификации файлов """
        if path in self.excludes:
            return True
        self.last_modified(path)
        return False

    @staticmethod
    def read_remotes(config):
        """ Читает конфигурацию репозитория """
        remote = re.compile(r'(remote|svn-remote)\.([^.]+)\.([^=]+)=(.*)')
        remotes = {'remote': {}, 'svn-remote': {}}
        for line in config:
            matcher = remote.match(line.decode('utf-8'))
            if matcher is not None:
                remote_type = matcher.group(1)
                name = matcher.group(2)
                key = matcher.group(3)
                value = matcher.group(4)
                remotes[remote_type].setdefault(name, {})
                remotes[remote_type][name][key] = value
        log.debug('remotes=%s', remotes)
        return remotes


class Backup:
    """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """

    @staticmethod
    def help():
        """ Выводит справку об использовании """
        print("Usage: backup.py command [options]")
        print("\ncommands:")
        print("\tfull srcDirs destDirs numberOfFiles -- dumps, clones and checks md5 sums")
        print("\tdump srcDirs destDirs [-h hostname] -- dumps source directories and writes md5 check sums")
        print("\tclone destDirs numberOfFiles -- checks md5 sums and clone archived files")
        print("\tgit srcDirs -- fetch srcDir Git repositories from remotes and push into remotes when --mirror=push")
        print("\tchecks destDirs -- checks md5 sums slow for low I/O load")
        print("\nExamples:")
        print("\tbackup.py full $HOME/src1,$HOME/src2 /local/backup,/remote/backup 3")
        print("\tbackup.py dump $HOME/src1,$HOME/src2 /var/backup")
        print("\tbackup.py clone /local/backup,/remote/backup2 5")
        print("\tbackup.py git $HOME/src1,$HOME/src2")
        print("\tbackup.py checks /local/backup1,/local/backup2")
        print()
        print("Optional config file $HOME/.config/backup/backup.cfg:")
        print("{")
        print('  "hostname": "myhost",')
        print('  "smtp_host": "smtp.mail.ru",')
        print('  "smtp_port": 425,')
        print('  "smtp_user": "user",')
        print('  "smtp_password": "password",')
        print('  "fromaddr": "backup@mail.ru",')
        print('  "toaddrs": "admin@mail.ru, admin2@mail.ru",')
        print('  "log_level": "DEBUG",')
        print('  "log_format": "%(levelname)5s %(lineno)3d %(message)s"')
        print("}")
        sys.exit()

    def __init__(self):
        """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
        self.config = {}
        self.arg_index = 1
        self.hostname = None
        self.smtp_host = None
        self.smtp_port = None
        self.smtp_user = None
        self.smtp_password = None
        self.from_address = None
        self.to_address = None
        # набор способов разделить нужные копии от избыточных
        self.time_separator: Optional[TimeSeparator] = None
        self.separators: List[Separator] = []
        self.src_dirs: List[str] = []
        self.dest_dirs: List[str] = []
        self.dir_set: Set[str] = set()
        self.new_checksum_by_path: Dict[str, str] = {}
        self.checksums_by_dir: Dict[str, Dict[str, Tuple[Optional[str], Optional[float]]]] = {}
        self.checked: float = time.time() - 30 * 24 * 3600
        self.strategies: Tuple[BackupStrategy, BackupStrategy] = (SvnBackup(self), GitBackup(self))
        self.commands: Dict[str, List[Callable[[], None]]] = {}  # команды на копирование/удаление файлов по директориям
        self.errors: List[str] = []
        self.strategy_dir: List[Tuple[BackupStrategy, str]] = []
        self.last_modified_time: float = -1

    def configure(self) -> Callable:
        """ Конфигурирует выполнение """
        self.config = self.read_config()
        level = log.getLevelName(self.config.get('log_level'))
        if level == 'Level None':
            level = log.INFO
        log_format = self.config.get('log_format')
        if log_format is None:
            # log_format = "%(levelname)5s %(lineno)3d %(message)s"
            log_format = "%(message)s"
        log.basicConfig(level=level, stream=sys.stdout, format=log_format)
        sys.setrecursionlimit(100)
        return self.command()

    @staticmethod
    def read_config() -> Dict[str, str]:
        """ Читает конфигурацию """
        try:
            with open(os.path.expanduser('~/.config/backup/backup.cfg'), encoding='UTF-8') as cfg:
                return json.load(cfg)
        except IOError:
            return {}

    def command(self) -> Callable:
        """ Вычисляет выполняемый метод """
        command = self.arg()
        src_dirs, dest_dirs, num = '', None, 3
        if "full" == command:
            method = self.full
            src_dirs = self.arg()
            dest_dirs = self.arg()
            num = int(self.arg())
        elif "dump" == command:
            method = self.dump
            src_dirs = self.arg()
            dest_dirs = self.arg()
        elif "clone" == command:
            method = self.clone
            dest_dirs = self.arg()
            num = int(self.arg())
        elif "git" == command:
            method = self.git
            src_dirs = self.arg()
        elif 'checks' == command:
            method = self.checks
            dest_dirs = self.arg()
        else:
            method = self.help
        self.hostname = self.config.get('hostname')
        if self.hostname is None:
            self.hostname = socket.gethostname()
        self.smtp_host = self.config.get('smtp_host')
        self.time_separator = TimeSeparator(num)
        self.separators = [self.time_separator, SvnSeparator()] # способы разделить нужные копии от избыточных
        self.src_dirs = src_dirs.split(',')
        log.debug("src_dirs=%s", self.src_dirs)
        self.dest_dirs = dest_dirs.split(',') if dest_dirs is not None else []
        log.debug("dest_dirs=%s", self.dest_dirs)
        for directory in self.dest_dirs:
            self.commands[directory] = []
        log.debug("self.commands=%s", self.commands)
        return method

    def main(self) -> None:
        """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
        stop_watch("backup", self.invoke)

    def invoke(self) -> None:
        """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий """
        # noinspection PyBroadException
        try:
            self.configure()()
        except BaseException:
            self.error("%s", traceback.format_exc())
        self.send_errors()

    def send_errors(self) -> None:
        """ Отправляет ошибки на почту """
        if len(self.errors) == 0:
            return
        smtp_port = self.config.get('smtp_port')
        server = smtplib.SMTP_SSL(self.smtp_host, smtp_port)
        try:
            user = self.config.get('smtp_user')
            password = self.config.get('smtp_password')
            server.login(user, password)
            msg = MIMEText('\n'.join(self.errors), 'plain', 'utf-8')
            msg['Subject'] = "backup error: " + self.hostname
            msg['From'] = self.config.get('fromaddr')
            msg['To'] = self.config.get('toaddrs')
            server.send_message(msg)
        finally:
            server.quit()

    def full(self) -> None:
        """ Архивирует исходные файлы и клонирует копии в несколько источников """
        self.dump()
        self.clone()

    def dump(self) -> None:
        """ Архивирует исходные файлы """
        for src in self.src_dirs:
            self.backup(src)
        dirs: Dict[str, List[str]] = dict()  # дочерние файлы по имени *.md5-файлов
        for path in self.new_checksum_by_path.keys():
            md5path = os.path.dirname(path) + '/.md5'
            lst = dirs.get(md5path)
            if lst is None:
                lst = dirs[md5path] = []
            lst.append(path)
        for md5path, lst in dirs.items():
            md5 = load_md5(md5path)
            for path in lst:
                name = os.path.basename(path)
                md5[name] = self.new_checksum_by_path[path]
            # TODO safe write
            with open(md5path, 'wb') as fd:
                names = list(md5.keys())
                names.sort()
                for name in names:
                    write_md5(fd, md5[name], name)

    def clone(self) -> None:
        """ Клонирует копии в несколько источников """
        self.recovery_dirs("")
        for dst in self.dest_dirs:
            for command in self.commands[dst]:
                command()

    def git(self) -> None:
        """ Выполняет fetch Git-репозиториев, и push, если настроен mirror push """
        for src in self.src_dirs:
            self.backup(src)

    def backup(self, src: str) -> None:
        """ Создаёт резервные копии директории """
        log.debug('backup(self, src=[%s]); self.destDirs=[%s]', src, self.dest_dirs)
        if '' == src:
            return
        self.last_modified_time = -1
        self.strategy_dir = []
        through_dirs(src, self.find_strategy, self.last_modified)
        prefix = self.hostname + '-' + os.path.basename(src)
        dst = self.dest_dirs[0] + '/' + self.hostname + '/' + prefix if len(self.dest_dirs) > 0 else None
        log.debug('backup: dst=[%s]', dst)
        if len(self.strategy_dir) == 0:
            self.safe_backup(None, src, dst, prefix)
        else:
            length = len(src)
            for strategy, directory in self.strategy_dir:
                if len(directory) == length:
                    self.safe_backup(strategy, directory, dst, prefix)
                else:
                    prf = prefix + directory[length:].replace('/', '-')
                    self.last_modified_time = -1
                    dst_prf = dst + '/' + prf if dst is not None else None
                    log.debug('backup: dst_prf=[%s]', dst_prf)
                    self.safe_backup(strategy, directory, dst_prf, prf)

    def find_strategy(self, directory: str) -> bool:
        """ Ищет способ резервного копирования.
            Устанавливает self.time последнее время модификации директории. """
        self.last_modified(directory)
        for strategy in self.strategies:
            if strategy.found(directory):
                self.strategy_dir.append((strategy, directory))
                return True
        return False

    def safe_backup(self, strategy: Optional[BackupStrategy], src: str, dst: str, prefix: str) -> None:
        """ Создаёт одиночную резервную копию. Перехватывает ошибки. """
        try:
            if strategy is None:
                if self.up_to_date(src, dst):
                    return
                self.generic_backup(src, dst, prefix)
            else:
                log.debug("strategy.backup('%s', '%s', '%s')", src, dst, prefix)
                strategy.backup(src, dst, prefix)
        except Exception as e:
            self.error("backup error:%s\n%s", e, traceback.format_exc())

    def generic_backup(self, src: str, dst: str, prefix: str) -> None:
        """ Полностью архивирует директорию, если не существует актуальной резервной копии """
        log.debug("generic backup(%s, %s, %s)", src, dst, prefix)
        if dst is None:
            log.debug('generic backup: ignore dst=[%s]', dst)
            return
        date = time.strftime("%Y-%m-%d")
        basename = os.path.basename(src)
        mkdirs(dst)
        path = dst + '/' + prefix + date + ".tar.gz"
        self.remove(path)
        self.new_checksum_by_path[path] = system(["tar", "cf", "-", basename],
                                                 GzipMd5sum(path),
                                                 cwd=os.path.dirname(src))
        key = path[len(self.dest_dirs[0]):]
        log.debug('key=%s', key)
        for dst in self.dest_dirs[1:]:
            self.remove(dst + key)

    def last_modified(self, path):
        """ Устанавливает self.last_modified_time последнее время модификации файла. """
        if not os.path.isfile(path):
            return
        modified = os.path.getmtime(path)
        if modified > self.last_modified_time:
            log.debug('last modified %s %s', modified, path)
            self.last_modified_time = modified

    def up_to_date(self, src, dst):
        """ Проверяет время создания последнего архива. Возвращает True, если backup не требуется """
        if dst is None:
            log.debug('dst=[%s] is up date.', dst)
            return True
        dst += '/'
        if not os.path.isdir(dst):
            return False
        entry_list = []
        for name in os.listdir(dst):
            if os.path.isfile(dst + name):
                entry, index = self.recovery_entry(name)
                if index == 0:  # TimeSeparator
                    log.debug('entry_list.append(%s)', entry)
                    entry_list.append(entry)
        entry_list = self.time_separator.separate(entry_list)[0]
        log.debug('list=%s', entry_list)
        if len(entry_list) > 0:
            path = dst + entry_list[0].name
            file_time = os.path.getmtime(path)
            checksum = self.checksum(path)[0]
            log.debug('time[%s]=%s, last_modified=%s, checksum=%s', path, file_time, self.last_modified, checksum)
            if file_time > self.last_modified_time and checksum is not None:
                log.info('[%s] is up to date.', src)
                return True
        return False

    def recovery_dirs(self, key: str) -> None:
        """ Восстанавливает повреждённые или отсутствующие файлы из зеркальных копий.
        Удаляет устаревшие копии """
        if key in self.dir_set:
            return
        log.debug("recovery dir %s", key)
        self.dir_set.add(key)
        log.debug('for dst in %s', self.dest_dirs)
        md5dirs, file_dict, recovery, lists = self.recovery_for_each_dest(key)
        if len(file_dict) == 0:
            return
        log.debug('for (name, entry) in in %s', file_dict)
        sw = StopWatch('md5sum -b %s%s/*' % (self.dest_dirs[0], key))
        remove = []
        for (name, entry) in file_dict.items():
            log.debug(' for (name=%s, entry=%s) in in %s', name, entry, file_dict)
            for dst in self.dest_dirs:
                path = dst + key + '/' + name
                md5 = self.new_checksum_by_path.get(path)
                if md5 is None:
                    md5, real = self.checksum(path)
                    if real:
                        md5dirs.add(dst)
                else:
                    md5dirs.add(dst)
                if md5 is None:
                    md5dirs.add(dst)
                    entry.list.append(dst)
                else:
                    if entry.dir is None:
                        entry.dir = dst
                    entry.md5[dst] = md5
        log.debug('for i in in range=%s', range(len(self.separators)))
        sw.stop()
        for i in range(len(self.separators)):
            rec, old = self.separators[i].separate(lists[i])
            recovery += rec
            remove += old
        log.debug("all=%s\n  recovery=%s\n  remove=%s", recovery + remove, recovery, remove)
        md5files = []
        for rec in recovery:
            k = key + '/' + rec.name
            if rec.dir is None:
                self.error("corrupt error: %s", k)
            else:
                md5files.append(rec)
                for dst in rec.list:
                    self.lazy_copy(rec, dst, k)
        for rec in remove:
            for dst in self.dest_dirs:
                self.lazy_remove(dst, key + '/' + rec.name)
        self.lazy_write_md5_to_md5dirs(md5dirs, key, md5files)

    def recovery_for_each_dest(self, key: str) -> Tuple[Set[str],
                                                        Dict[str, RecoveryEntry],
                                                        List[RecoveryEntry],
                                                        Tuple[List[RecoveryEntry], List[RecoveryEntry]]]:
        """ Вызывает recovery_for_each для всех целевых каталогов """
        md5dirs: Set[str] = set()  # контрольные суммы этих каталогов будут перезаписаны
        file_dict: Dict[str, RecoveryEntry] = {}
        recovery: List[RecoveryEntry] = []
        lists: Tuple[List[RecoveryEntry], List[RecoveryEntry]] = ([], [])

        def recovery_key_search(dest: str, file: str) -> None:
            self.recovery_key_search(dest, key + '/' + file, file, md5dirs, file_dict, recovery, lists)

        for dst in self.dest_dirs:
            log.debug('for dst=%s in %s', dst, self.dest_dirs)
            self.recovery_for_each(dst, key, recovery_key_search)

        return md5dirs, file_dict, recovery, lists

    @staticmethod
    def recovery_for_each(dst: str, key: str, recovery_key_search: Callable[[str, str], None]) -> None:
        """ Вызывает recovery_key_search для всех дочерних файлов/каталогов """
        path = dst + key
        if not os.path.isdir(path):
            log.debug('continue')
            return
        listdir = os.listdir(path)
        log.debug('for name in %s', listdir)
        for name in listdir:
            log.debug('for name=%s in os.listdir.path(%s)', name, path)
            recovery_key_search(dst, name)

    def recovery_key_search(self,
                            dst: str,
                            key: str,
                            name: str,
                            md5dirs: Set[str],
                            file_dict: Dict[str, RecoveryEntry],
                            recovery: List[RecoveryEntry],
                            lists: Tuple[List[RecoveryEntry], List[RecoveryEntry]]) -> None:
        """
        Исследует файл/каталог dst + key:
          * вызывает рекурсивно для дочерних каталогов recovery_dirs;
          * файлы с контрольными суммами, *.md5;
          * запоминает в md5dirs каталоги, для которых должны сохраниться контрольные суммы.
          * RecoveryEntry всех хранимых файлов бэкапов запоминает в file_dict[name].
          * Накапливает в recovery RecoveryEntry файлов, которые безусловно должны остаться в бэкапе.
          * Накапливает в lists RecoveryEntry файлов, которые могут удаляться из бэкапа по условию.
        """
        path = dst + key
        if os.path.isdir(path):
            log.debug('enter into self.recovery_dirs(%s)', key)
            self.recovery_dirs(key)
            log.debug('leave from self.recovery_dirs(%s)', key)
        elif os.path.isfile(path):
            if name.endswith(".md5"):
                if name != ".md5":
                    md5dirs.add(dst)
            elif name not in file_dict and key not in ('/.checksum', '/.lock'):
                entry, index = self.recovery_entry(name)
                file_dict[name] = entry
                if index < 0:
                    log.debug('recovery.append(%s)', name)
                    recovery.append(entry)
                else:
                    log.debug('lists[%s].append(%s)', index, name)
                    lists[index].append(entry)

    def checks(self) -> None:
        """ Выполняет медленную проверку контрольных сумм, чтоб не создавать нагрузку на систему. """
        def check():
            for path in self.dest_dirs:
                self.check_dir_recursively(path)
        with_lock_file(self.dest_dirs[0] + '/.lock', check)

    def check_dir_recursively(self, directory: str) -> None:
        """ Выполняет медленную проверку контрольных сумм, чтоб не создавать нагрузку на систему. """
        for root, dirs, files in os.walk(directory):
            self.check_dir(root, root + '/.checksum', set(files))

    def check_dir(self, directory: str, checksum_path: str, files: Set[str]) -> None:
        md5_with_time = self.read_dir_md5_with_time(directory, checksum_path, files)
        if len(md5_with_time) == 0:
            remove_file(checksum_path)
        elif self.safe_write(checksum_path,
                             lambda fd: self.write_md5_with_time_dict(fd, md5_with_time),
                             lambda: 'update ' + checksum_path):
            self.slow_check_dir(directory, checksum_path, md5_with_time)

    @classmethod
    def read_dir_md5_with_time(cls,
                               directory: str,
                               checksum_path: str,
                               files: Set[str]) -> Dict[str, Tuple[str, float]]:
        """ Возвращает контрольные суммы из лога и файлов *.md5 в директории """
        log_md5_with_time = load_md5_with_times(checksum_path)
        dir_md5_with_time = {key: log_md5_with_time[key]
                             for key in filter(lambda f: f in files, log_md5_with_time)}
        for name in filter(lambda f: f.endswith('.md5'), files):
            cls.update_dir_md5_with_time(dir_md5_with_time, directory, name, files)
        return dir_md5_with_time

    @staticmethod
    def update_dir_md5_with_time(dir_md5_with_time: Dict[str, Tuple[str, float]],
                                 directory: str,
                                 md5_name: str,
                                 files: Set[str]) -> None:
        """ Дописывает в dir_md5_with_time записи из файла *.md5 """
        md5_sums = load_md5(directory + '/' + md5_name)
        for name, checksum in filter(lambda i: i[0] in files, md5_sums.items()):
            sum_time = os.path.getmtime(directory + '/' + name)
            if name not in dir_md5_with_time or sum_time > dir_md5_with_time[name][1]:
                dir_md5_with_time[name] = (checksum, sum_time)

    @classmethod
    def slow_check_dir(cls, directory: str, checksum_path: str, md5_with_time: Dict[str, Tuple[str, float]]):
        """ Медленно пересчитывает контрольные суммы, чтоб не создавать нагрузку на систему """
        for key in cls.sorted_md5_with_time_by_time(md5_with_time):
            sum_time = time.time()
            s = md5sum(directory + '/' + key, multiplier=cls.with_sleep_multiplier)
            if s != md5_with_time[key][0]:
                s = 'corrupted'
            with_open(checksum_path, 'ab', lambda fd: cls.write_md5_with_time(fd, key, s, sum_time))

    @classmethod
    def write_md5_with_time_dict(cls, fd: IO, md5_with_time: Dict[str, Tuple[str, float]]) -> None:
        """ Перезаписывает с контрольными суммами md5 """
        for k in cls.sorted_md5_with_time_by_time(md5_with_time):
            md5_sum, sum_time = md5_with_time[k]
            cls.write_md5_with_time(fd, k, md5_sum, sum_time)

    @staticmethod
    def write_md5_with_time(fd: IO, key: str, checksum: str, sum_time: float) -> None:
        """ Записывает в лог-файл одну запись"""
        fd.write(bytes('%s %s %s\n' % (checksum, time_to_string(sum_time), key), 'UTF-8'))

    @staticmethod
    def with_sleep_multiplier():
        """ Спит 10 ms каждые 4 кБайт. 1 ГБайт обработает не менее чем за 43 минуты """
        time.sleep(0.01)
        return 4

    @staticmethod
    def sorted_md5_with_time_by_time(md5_with_time):
        return sorted(md5_with_time, key=lambda k: md5_with_time[k][1])

    def recovery_entry(self, name: str) -> Tuple[RecoveryEntry, int]:
        """ Возвращает созданный RecoveryEntry и индекс классификатора имён файлов """
        entry = RecoveryEntry(name)
        for i in range(len(self.separators)):
            separator = self.separators[i]
            matcher = separator.pattern.match(name)
            if matcher is not None:
                separator.init(entry, matcher)
                return entry, i
        return entry, -1

    def lazy_copy(self, rec: RecoveryEntry, dst: str, key: str) -> None:
        """ Выполняет отложенное копирование файла """
        log.debug("lazy cp %s%s %s%s", rec.dir, key, dst, key)
        self.commands[dst].append(lambda: self.copy(rec, dst, key))

    def lazy_remove(self, dst: str, key: str) -> None:
        """ Выполняет отложенное удаление файла """
        path = dst + key
        log.debug("lazy rm %s", path)
        self.commands[dst].append(lambda: self.remove(path))

    def lazy_write_md5_to_md5dirs(self, md5dirs: Iterable[str], key: str, md5files: List[RecoveryEntry]) -> None:
        """ Выполняет отложенную запись контрольной суммы в каталоги """
        for dst in md5dirs:
            self.lazy_write_md5(dst, key, md5files)

    def lazy_write_md5(self, dst: str, key: str, md5files: List[RecoveryEntry]) -> None:
        """ Выполняет отложенную запись контрольной суммы """
        log.debug("lazy md5sum -b * > %s%s/.md5", dst, key)
        self.commands[dst].append(lambda: self.write_md5(dst, key, md5files))

    def write_md5(self, dst: str, key: str, md5files: List[RecoveryEntry]) -> None:
        """ Пишет контрольные суммы в файл """
        directory = dst + key
        path = directory + "/.md5"
        self.safe_write(path, lambda fd: self.do_write_md5(fd, dst, md5files), lambda: "md5sum -b %s/*" % dst + key)

    @staticmethod
    def do_write_md5(fd: BinaryIO, dst: str, md5files: List[RecoveryEntry]) -> None:
        """ Пишет контрольные суммы в файл """
        for rec in md5files:
            if dst in rec.md5:
                write_md5(fd, rec.md5[dst], rec.name)

    def safe_write(self, file: str, write: Callable[[IO], None], name: Callable[[], str]) -> bool:
        """ Безопасно пишет в файл """
        tmp = file + ".tmp"
        try:
            remove_file(tmp)
            mkdirs(os.path.dirname(file))
            with open(tmp, "wb") as fd:
                write(fd)
            remove_file(file)
            os.rename(tmp, file)
            return True
        except Exception as e:
            self.error("%s error: %s\n%s", name(), e, traceback.format_exc())
            return False
        finally:
            self.safe_remove(tmp)

    def safe_remove(self, path: str) -> None:
        """ Удаляет файл с подавлением исключений """
        try:
            self.remove(path)
        except Exception as e:
            self.error("[rm %s] error: %s\n%s", path, e, traceback.format_exc())

    @staticmethod
    def remove(path: str) -> None:
        """ Удаляет файл """
        if os.path.isfile(path):
            sw = StopWatch("rm %1s" % path)
            remove_file(path)
            sw.stop()

    def copy(self, rec: RecoveryEntry, dst_dir: str, key: str) -> None:
        """ Копирует файл """
        # быстрее всего копировать с 1-й директории, с локального диска
        src_dir = rec.dir if dst_dir == self.dest_dirs[0] else self.dest_dirs[0]
        src = src_dir + key
        dst = dst_dir + key
        sw = StopWatch("cp %s %s" % (src, dst))
        if self.safe_write(dst, lambda out: self.do_copy(out, src, rec.md5[rec.dir]), lambda: "cp %s %s" % (src, dst)):
            rec.md5[dst_dir] = rec.md5[rec.dir]
        sw.stop()

    @staticmethod
    def do_copy(out: IO, src: str, expected: str) -> None:
        def copy(fd: IO):
            checksum = hashlib.md5()
            while True:
                buf = fd.read(1024 * 1024)
                if len(buf) == 0:
                    return checksum.hexdigest().lower()
                checksum.update(buf)
                out.write(buf)
        actual = with_open(src, 'rb', copy)
        if actual != expected:
            raise IOError('Corrupted [%s]. Checksum is %s but expected %s' % (src, actual, expected))

    def checksum(self, path: str) -> Tuple[Optional[str], bool]:
        """ Проверяет контрольную сумму файла. Возвращает её, или None, если сумма не верна
            и флаг, что сумма была вычислена, а не взята из файла. Вычисленная будет перезаписана """
        directory = os.path.dirname(path)
        name = os.path.basename(path)
        checksum_by_name = self.checksum_by_name(directory)
        stored, file_time = checksum_by_name.get(name, (None, None))
        # file_time is None в двух случаях:
        # 1) когда и stored is None, контрольной суммы нет
        # 2) контрольная сумма только что вычислена заново
        if file_time is None or self.checked < file_time:
            return stored, False
        try:
            real = md5sum(path, is_stop_watch=False)
            if stored != real:
                stored = None
            checksum_by_name[name] = (stored, None)
            return stored, True
        except Exception as e:
            self.error("new checksum check error: %s", e)
            checksum_by_name[name] = (None, None)
            return None, False

    def checksum_by_name(self, directory: str) -> Dict[str, Tuple[Optional[str], Optional[float]]]:
        """ Возвращает контрольные суммы файлов в директории из *.checksum и файлов *.md5. Кэширует результат """
        result = self.checksums_by_dir.get(directory)
        if result is not None:
            return result
        for root, dirs, files in os.walk(directory):
            result = self.read_dir_md5_with_time(directory, directory + '/.checksum', set(files))
            break
        if result is None:
            result = {}
        self.checksums_by_dir[directory] = result
        return result

    def error(self, msg, *args):
        """ Пишет сообщение в лог. Добавляет сообщение для отправки email """
        log.error(msg, *args)
        if self.smtp_host is not None:
            self.errors.append(msg % args)

    def arg(self):
        """ Возвращает sys.arg[self.arg_index], или выводит справку и завершает работу """
        if len(sys.argv) > self.arg_index:
            arg = sys.argv[self.arg_index]
            self.arg_index += 1
            return arg
        self.help()


def with_lock_file(path, handler):
    def lock(fd):
        if lock_file(fd):
            remove = atexit.register(lambda: remove_file(path))
            handler()
            return remove
        return None

    try:
        rm = with_open(path, 'xb', lock)
    except FileExistsError:
        rm = with_open(path, 'r+b', lock)
    if rm is not None:
        remove_file(path)
        atexit.unregister(rm)


def lock_file(fd: BinaryIO) -> bool:
    import fcntl
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except IOError:
        return False


def time_to_string(sec: float) -> str:
    s = time.strftime('%Y-%m-%dT%X%z', time.localtime(sec))
    micros = int((sec - int(sec)) * 1000000)
    return '%s.%06d%s:%s' % (s[0:-5], micros, s[-5:-2], s[-2:])


def time_from_string(iso: str) -> float:
    s = '%s%s%s' % (iso[0:-13], iso[-6:-3], iso[-2:])
    micros = int(iso[-12:-6]) / 1000000.0
    return time.mktime(time.strptime(s, '%Y-%m-%dT%X%z')) + micros


if __name__ == '__main__':
    Backup().main()
