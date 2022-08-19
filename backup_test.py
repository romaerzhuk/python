import hashlib
import json
import logging
import math
import os.path
import time
from typing import Callable
from unittest import TestCase
from unittest import mock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import call
from unittest.mock import patch

import backup
from backup import Backup
from backup import SvnBackup
from backup import SvnSeparator
from backup import TimeSeparator


class BackupUnitTest(TestCase):

    @patch('backup.time', autospec=True)
    @patch('backup.log', autospec=True)
    def test_stop_watch(self, mock_log, mock_time):
        msg = 'msg%s' % uid()
        stop = uid_time()
        start = uid_time()
        mock_time.time.side_effect = [start, stop]
        result = uid()

        def func():
            mock_time.time.assert_called_once_with()
            return result

        self.assertEqual(backup.stop_watch(msg, func), result)

        mock_log.info.assert_called_once_with("[%s]: %1.3f sec", msg, stop - start)

    @patch('backup.os.path', autospec=True)
    @patch.object(backup, 'stop_watch', spec=backup.stop_watch)
    @patch.object(backup, 'with_open', spec=backup.with_open)
    def test_md5sum(self, mock_with_open, mock_stop_watch, mock_path):
        import hashlib
        args = [(is_input_stream, out, is_stop_watch, multiplier, is_file)
                for is_input_stream in (False, True)
                for out in (None, Mock(name='out'))
                for is_stop_watch in (False, True)
                for multiplier in (None, Mock(name='multiplier'))
                for is_file in (False, True)]
        for is_input_stream, out, is_stop_watch, multiplier, is_file in args:
            with self.subTest(is_input_stream=is_input_stream, out=out, is_stop_watch=is_stop_watch,
                              multiplier=multiplier, is_file=is_file):
                for m in (mock_with_open, mock_stop_watch, mock_path, out, multiplier):
                    if m is not None:
                        m.reset_mock()
                input_stream = Mock(name='input_stream')
                path = 'path-%s' % uid()
                mock_path.isfile.return_value = is_file

                def stop_watch(msg, func):
                    self.assertEqual(msg, 'md5sum -b %s' % path)
                    return func()

                mock_stop_watch.side_effect = stop_watch
                if multiplier is None:
                    multiplier_value = 1024
                else:
                    multiplier_value = uid()
                    multiplier.return_value = multiplier_value
                data = [bytes('data-%s' % uid(), 'UTF-8')] * (3 + uid(5)) + [b'']
                input_stream.read.side_effect = data
                md5 = hashlib.md5()
                for i in data:
                    md5.update(i)
                expected = md5.hexdigest().lower() if is_input_stream or is_file else None

                def with_open(name, mode, handler):
                    self.assertEqual((name, mode), (path, 'rb'))
                    return handler(input_stream)

                mock_with_open.side_effect = with_open

                self.assertEqual(backup.md5sum(path, input_stream if is_input_stream else None,
                                               out, is_stop_watch, multiplier), expected)

                if not is_input_stream and not is_file:
                    mock_with_open.assert_not_called()
                    mock_stop_watch.assert_not_called()
                    if out is not None:
                        out.write.assert_not_called()
                else:
                    if is_input_stream:
                        mock_path.isfile.assert_not_called()
                        mock_with_open.assert_not_called()
                        input_stream.read.assert_has_calls([call(1024 * multiplier_value)] * len(data))
                    else:
                        mock_path.isfile.assert_called_once_with(path)
                        mock_with_open.assert_called_once()
                        if is_stop_watch:
                            mock_stop_watch.assert_called_once()
                        else:
                            mock_stop_watch.assert_not_called()
                    if out is not None:
                        out.write.assert_has_calls([call(i) for i in data[0:len(data) - 1]])

    @patch('backup.os.path', autospec=True)
    def test_load_md5(self, mock_path):
        for is_file in (False, True):
            with self.subTest(is_file=is_file):
                mock_path.reset_mock()
                path = 'path-%s' % uid()
                mock_path.isfile.return_value = is_file
                name1, sum1 = 'name1-%s' % uid(), 'sum1-%s' % uid()
                name2, sum2 = 'name2-%s' % uid(), 'sum2-%s' % uid()
                name3, sum3 = 'name2-%s' % uid(), 'sum2-%s' % uid()
                data = '%s  *%s\n'\
                       'any%s\n'\
                       '%s \t *%s\n'\
                       '%s\t*%s' % (sum1.upper(), name1, uid(), sum2, name2, sum3.upper(), name3)
                with patch('builtins.open', new_callable=mock.mock_open, read_data=data) as mock_file:

                    result = backup.load_md5(path)

                    mock_path.isfile.assert_called_once_with(path)
                    self.assertEqual(result, {name1: sum1, name2: sum2, name3: sum3} if is_file else {})
                    mock_file.assert_has_calls([call(path, encoding='UTF-8')] if is_file else [])

    @patch('backup.os.path', autospec=True)
    @patch.object(backup, 'with_open', spec=backup.with_open)
    def test_load_md5_with_times(self, mock_with_open, mock_path):
        for is_file in (False, True):
            with self.subTest(is_file=is_file):
                mock_with_open.reset_mock()
                mock_path.reset_mock()
                mock_path.isfile.return_value = is_file

                def uid_spaces():
                    return ' ' * (1 + uid(3)) + '\t' * (uid(3))

                expected = {'name-%s' % uid(): ('sum-%s' % uid(), int(uid_time()))
                            for _ in uid_range()}
                data = [expected[key][0] + uid_spaces() + time_to_iso(expected[key][1]) + uid_spaces() + key
                        for key in expected]
                data.insert(1, 'sum-%s no matched value name-%s' % (uid(), uid()))
                data.insert(1, 'sum-%s 2021-99-99T99:99:99.123456+00:00 name-%s' % (uid(), uid()))  # illegal time
                path = 'path-%s' % uid()

                def with_open(name, mode, read):
                    self.assertEqual((name, mode), (path, 'r'))
                    return read(data)

                mock_with_open.side_effect = with_open

                actual = backup.load_md5_with_times(path)

                self.assertEqual(actual, {} if not is_file else expected)
                mock_path.isfile.assert_called_once_with(path)

    def test_with_open(self):
        for binary in (False, True):
            with self.subTest(binary=binary):
                handler = Mock()
                result = uid()
                handler.return_value = result
                with patch('builtins.open', new_callable=mock.mock_open) as mock_file:
                    path = 'path-%s' % uid()
                    mode = 'mode%s-%s' % (uid(), 'b' if binary else '')

                    self.assertEqual(backup.with_open(path, mode, handler), result)

                    mock_file.assert_called_once_with(path, mode, encoding=None if binary else 'UTF-8')


class SvnBackupTest(TestCase):

    @patch('backup.system', autospec=True)
    def test_svn_revision(self, mock_system):
        subj = Backup()
        subj = SvnBackup(subj)
        for src in (str(uid()), "/%s" % uid(), "../%s" % uid()):
            with self.subTest(src=src):
                expected = uid()
                mock_system.reset_mock()
                mock_system.return_value = expected
                url = "file://" + os.path.abspath(src)

                self.assertEqual(subj.svn_revision(src), expected)
                mock_system.assert_called_once_with(("svn", "info", url), subj.read_revision)
                self.assertTrue(".." in "../%s" % uid())
                self.assertFalse(".." in url)


# noinspection PyTypeChecker
class BackupTest(TestCase):

    @patch("backup.time", autospec=True)
    def test_init(self, mock_time):
        now = uid_time()
        mock_time.time.return_value = now
        subj = Backup()

        self.assertEqual(time_to_iso(subj.checked), time_to_iso(now - 30 * 24 * 3600))

    @patch("backup.sys", autospec=True)
    @patch("backup.log", autospec=True)
    @patch.object(Backup, "read_config", spec=Backup.read_config)
    @patch.object(Backup, "command", autospec=True)
    def test_configure(self, mock_command, mock_read_config, mock_log, mock_sys):
        for log_level in (None, logging.DEBUG, logging.INFO, logging.ERROR):
            for log_format in (None, str(uid())):
                with self.subTest(log_level=log_level, log_format=log_format):
                    subj = Backup()
                    mock_log.reset_mock()
                    mock_sys.reset_mock()
                    config = {}
                    command = uid()
                    mock_command.return_value = command
                    mock_read_config.return_value = config
                    if log_format is not None:
                        config['log_format'] = log_format
                    if log_level is not None:
                        config['log_level'] = logging.getLevelName(log_level)
                    mock_log.getLevelName.side_effect = logging.getLevelName

                    self.assertEqual(subj.configure(), command)

                    mock_log.basicConfig.assert_called_once_with(
                        level=mock_log.INFO if log_level is None else log_level,
                        stream=mock_sys.stdout,
                        format="%(message)s" if log_format is None else log_format)
                    mock_sys.setrecursionlimit.assert_called_once_with(100)

    @patch('backup.os.path', autospec=True)
    def test_read_config(self, mock_path):
        subj = Backup()
        path = str(uid())
        mock_path.expanduser.return_value = path
        config = {'a': uid(), 'b': uid()}
        data = json.dumps(config)
        with patch('builtins.open', new_callable=mock.mock_open, read_data=data) as mock_file:
            self.assertEqual(subj.read_config(), config)
        mock_path.expanduser.assert_called_once_with('~/.config/backup/backup.cfg')
        mock_file.assert_called_once_with(path, encoding='UTF-8')

    @patch('backup.socket', autospec=True)
    @patch('backup.TimeSeparator', autospec=True)
    @patch('backup.SvnSeparator', autospec=True)
    @patch.object(Backup, 'arg', autospec=True)
    def test_command(self, mock_arg, mock_svn_separator, mock_time_separator, mock_socket):
        subj = Backup()
        for command, method, has_src_dirs, has_dst_dirs in (
                ('full', subj.full, True, True),
                ('dump', subj.dump, True, True),
                ('clone', subj.clone, False, True),
                ('git', subj.git, True, False),
                ('checks', subj.checks, False, True),
                ('any', subj.help, False, False),
                (str(uid()), subj.help, False, False)):
            for empty in (False, True):
                with self.subTest(command=command, empty=empty):
                    mock_time_separator.reset_mock()
                    mock_svn_separator.reset_mock()
                    subj.commands = {}
                    src_dirs = ['src%s-%s' % (i, uid()) for i in uid_range()]
                    dest_dirs = ['dst%s-%s' % (i, uid()) for i in uid_range()]
                    num = uid()
                    command_line = [command]
                    if has_src_dirs:
                        command_line.append(','.join(src_dirs))
                    if has_dst_dirs:
                        command_line.append(','.join(dest_dirs))
                    command_line.append(str(num))
                    mock_arg.side_effect = command_line
                    hostname = 'hostname%s' % uid()
                    smtp_host = 'smtp_host%s' % uid()
                    subj.config = {} if empty else {'hostname': hostname, 'smtp_host': smtp_host}
                    mock_socket.gethostname.return_value = hostname if empty else None
                    commands = {}
                    if not has_dst_dirs:
                        dest_dirs = []
                    else:
                        for dst in dest_dirs:
                            commands[dst] = []

                    result = subj.command()

                    self.assertEqual(result, method)
                    self.assertEqual(subj.hostname, hostname)
                    self.assertEqual(subj.smtp_host, None if empty else smtp_host)
                    self.assertTrue(isinstance(subj.time_separator, TimeSeparator))
                    mock_time_separator.assert_called_once_with(
                        num if command == 'full' or command == 'clone' else 3)
                    mock_svn_separator.assert_called_once_with()
                    self.assertEqual(subj.separators[0], subj.time_separator)
                    self.assertTrue(isinstance(subj.separators[1], SvnSeparator))
                    self.assertEqual(len(subj.separators), 2)
                    self.assertEqual(subj.src_dirs, src_dirs if has_src_dirs else [''])
                    self.assertEqual(subj.dest_dirs, dest_dirs if has_dst_dirs else [])
                    self.assertEqual(subj.commands, commands)

    @patch('backup.stop_watch', autospec=True)
    def test_main(self, mock_stop_watch):
        subj = Backup()
        subj.main()
        mock_stop_watch.assert_called_once_with('backup', subj.invoke)

    @patch('backup.traceback', autospec=True)
    @patch.object(Backup, 'configure', autospec=True)
    @patch.object(Backup, 'error', autospec=True)
    @patch.object(Backup, 'send_errors', autospec=True)
    def test_invoke(self, mock_send_errors, mock_error, mock_configure, mock_traceback):
        for thrown in [None, BaseException, Exception, IOError]:
            trace = 'trace-%s' % uid()

            def invoke():
                mock_send_errors.assert_not_called()
                if thrown:
                    raise thrown

            def format_exc():
                mock_send_errors.assert_not_called()
                return trace

            with self.subTest(thrown=thrown):
                for m in (mock_send_errors, mock_error, mock_configure, mock_traceback):
                    m.reset_mock()
                subj = Backup()
                method = Mock()
                method.side_effect = invoke
                mock_configure.return_value = method
                mock_traceback.format_exc.side_effect = format_exc

                subj.invoke()

                if thrown:
                    mock_error.assert_called_once_with(subj, "%s", trace)
                else:
                    mock_error.assert_not_called()
                mock_send_errors.assert_called_once_with(subj)

    @patch('backup.smtplib.SMTP_SSL', autospec=True)
    @patch('backup.MIMEText', autospec=True)
    def test_send_errors(self, mime_text, smtp_ssl):
        for thrown in [None, BaseException(), Exception(), IOError()]:
            for empty in (False, True):
                with self.subTest(thrown=thrown, empty=empty):
                    for m in (mime_text, smtp_ssl):
                        m.reset_mock()
                    subj = Backup()
                    errors = [] if empty else ['err-%s' % uid(), 'err-%s' % uid()]
                    subj.errors = errors
                    hostname = 'hostname-%s' % uid()
                    subj.hostname = hostname
                    subj.smtp_host = 'smtp_host-%s' % uid()
                    port = uid()
                    user = 'user-%s' % uid()
                    password = 'password-%s' % uid()
                    from_address = 'from-%s' % uid()
                    to_address = 'to-%s' % uid()
                    subj.config = {'smtp_port': port,
                                   'smtp_user': user,
                                   'smtp_password': password,
                                   'fromaddr': from_address,
                                   'toaddrs': to_address}
                    server = Mock()
                    smtp_ssl.return_value = server
                    message = MagicMock()

                    def send_message(msg):
                        self.assertEqual(msg, message)
                        server.login.assert_called_once_with(user, password)
                        mime_text.assert_called_once_with('\n'.join(errors), 'plain', 'utf-8')
                        message.__setitem__.assert_has_calls([
                            call('Subject', "backup error: " + hostname),
                            call('From', from_address),
                            call('To', to_address)
                        ])
                        server.quit.assert_not_called()
                        if thrown:
                            raise thrown

                    mime_text.return_value = message
                    server.send_message.side_effect = send_message

                    # noinspection PyBroadException
                    try:
                        subj.send_errors()
                    except BaseException as e:
                        if e != thrown:
                            raise e

                    if not empty:
                        server.send_message.assert_called_once_with(message)
                        server.quit.assert_called_once_with()
                    else:
                        smtp_ssl.assert_not_called()
                        server.login.assert_not_called()
                        server.quit.assert_not_called()

    def test_recovery_for_each_dest(self):
        subj = Backup()
        key = 'key-%s'
        # TODO возвращать результат. Перенести конструирование recovery_key_search внутрь recovery_for_each_dest

        subj.recovery_for_each_dest(key)

        self.fail("TODO")

    @patch('backup.os', autospec=True)
    def test_recovery_for_each(self, mock_os):
        for isdir in (False, True):
            with self.subTest(isdir=isdir):
                mock_os.reset_mock()
                subj = Backup()
                dst = 'dst-%s' % uid()
                key = 'key-%s'
                recovery_key_search = Mock()
                mock_os.path.isdir.return_value = isdir
                mock_os.listdir.return_value = listdir = ['name-%s' % uid() for _ in uid_range()]

                subj.recovery_for_each(dst, key, recovery_key_search)

                mock_os.path.isdir.assert_called_once_with(dst + key)
                if isdir:
                    mock_os.listdir.assert_called_once_with(dst + key)
                    recovery_key_search.assert_has_calls([call(dst, name) for name in listdir])
                else:
                    mock_os.listdir.assert_not_called()
                    recovery_key_search.assert_not_called()

    @patch('backup.os', autospec=True)
    @patch.object(Backup, 'recovery_dirs', autospec=True)
    @patch.object(Backup, 'recovery_entry', autospec=True)
    def test_recovery_key_search(self, mock_recovery_entry, mock_recovery_dirs):
        subj = Backup()
        dst = 'dst-%s' % uid()
        key = 'key-%s' % uid()
        name = 'name-%s' % uid()
        md5dirs = ['md5dirs-%s' % uid() for _ in uid_range()]
        file_dict = {'file-%s' % uid():  uid() for _ in uid_range()}
        recovery = ['recovery-%s' % uid() for _ in uid_range()]
        indexes = [uid() for _ in uid_range()]
        lists = {i: ['list-%s' % uid() for _ in uid_range()] for i in indexes}

        subj.recovery_key_search(dst, key, name, md5dirs, file_dict, recovery, lists)

        self.fail("TODO")

    @patch.object(Backup, 'check_dir_recursively', autospec=True)
    @patch.object(backup, 'with_lock_file', spec=backup.with_lock_file)
    def test_checks(self, mock_with_lock_file, mock_check_dir_recursively):
        subj = Backup()
        dirs = ['dir-%s' % uid() for _ in uid_range()]
        subj.dest_dirs = dirs

        def with_lock_file(path, handler):
            mock_check_dir_recursively.assert_not_called()
            self.assertEqual(path, dirs[0] + '/.lock')

            handler()
            mock_check_dir_recursively.assert_has_calls([call(subj, i) for i in dirs])
        mock_with_lock_file.side_effect = with_lock_file

        subj.checks()

        mock_with_lock_file.assert_called_once_with(dirs[0] + '/.lock', mock.ANY)

    @patch('backup.os', autospec=True)
    @patch.object(Backup, 'check_dir', autospec=True)
    def test_check_dir_recursively(self, mock_check_dir, mock_os):
        subj = Backup()
        directory = 'dir-%s' % uid()
        walk = [('root-%s' % uid(), 'dirs-%s' % uid(), ['file-%s' % uid() for _ in uid_range()])
                for _ in uid_range()]
        mock_os.walk.return_value = walk
        expected_calls = [call(subj, root, root + '/.checksum', set(files)) for root, _, files in walk]

        subj.check_dir_recursively(directory)

        mock_check_dir.assert_has_calls(expected_calls)

    @patch.object(Backup, 'read_dir_md5_with_time', spec=Backup.read_dir_md5_with_time)
    @patch.object(backup, 'remove_file', spec=backup.remove_file)
    @patch.object(Backup, 'safe_write', autospec=True)
    @patch.object(Backup, 'write_md5_with_time_dict', spec=Backup.write_md5_with_time_dict)
    @patch.object(Backup, 'slow_check_dir', spec=Backup.slow_check_dir)
    def test_check_dir(self, mock_slow_check_dir, mock_write_md5_with_time_dict,
                       mock_safe_write, mock_remove_file,
                       mock_read_dir_md5_with_time):
        for is_safe_write in (False, True):
            for md5_with_time_len in uid_range():
                for m in (mock_slow_check_dir, mock_write_md5_with_time_dict,
                          mock_safe_write, mock_remove_file,
                          mock_read_dir_md5_with_time):
                    m.reset_mock()
                with self.subTest(is_safe_write=is_safe_write, md5_with_time_len=md5_with_time_len):
                    subj = Backup()
                    md5_with_time = [uid() for _ in range(0, md5_with_time_len)]
                    checksum_path = 'checksum_path-%s' % uid()

                    def safe_write(slf, file, write, name):
                        mock_write_md5_with_time_dict.assert_not_called()
                        self.assertEqual((slf, file, name()), (subj, checksum_path, 'update %s' % checksum_path))
                        fd = uid()

                        write(fd)
                        mock_write_md5_with_time_dict.assert_called_once_with(fd, md5_with_time)
                        return is_safe_write
                    mock_read_dir_md5_with_time.return_value = md5_with_time
                    mock_safe_write.side_effect = safe_write
                    directory = 'directory-%s' % uid()
                    files = {'file-%s' % uid() for _ in uid_range()}

                    subj.check_dir(directory, checksum_path, files)

                    mock_read_dir_md5_with_time.assert_called_once_with(directory, checksum_path, files)
                    mock_remove_file.assert_has_calls([] if md5_with_time_len > 0
                                                      else [call(checksum_path)])
                    mock_safe_write.assert_has_calls([] if md5_with_time_len == 0
                                                     else [call(subj, checksum_path, mock.ANY, mock.ANY)])
                    mock_slow_check_dir.assert_has_calls([] if md5_with_time_len == 0 or not is_safe_write
                                                         else [call(directory, checksum_path, md5_with_time)])

    @patch.object(backup, 'load_md5_with_times', spec=backup.load_md5_with_times)
    @patch.object(Backup, 'update_dir_md5_with_time', spec=Backup.update_dir_md5_with_time)
    def test_read_dir_md5_with_time(self, mock_update_dir_md5_with_time, mock_load_md5_with_times):
        subj = Backup()
        directory = 'directory-%s' % uid()
        checksum_path = 'checksum_path-%s' % uid()
        targets = ['file-%s.any%s' % (uid(), uid()) for _ in uid_range()]  # целевые файлы
        md5_files = ['file-%s.md5' % uid() for _ in uid_range()]  # файлы .md5
        files = targets + md5_files + ['file-%s.any%s' % (uid(), uid()) for _ in uid_range()]  # + другие файлы
        dir_md5_with_time = {f: uid() for f in targets}  # целевой результат
        log_md5_with_time = dir_md5_with_time.copy()
        log_md5_with_time.update({'file-%s.any%s' % (uid(), uid()): uid()
                                  for _ in uid_range()})   # файлы, которых уже нет, игнорируются
        mock_load_md5_with_times.return_value = log_md5_with_time
        expected_calls = [call(dir_md5_with_time, directory, i, files) for i in md5_files]

        actual = subj.read_dir_md5_with_time(directory, checksum_path, files)

        self.assertEqual(actual, dir_md5_with_time)
        mock_load_md5_with_times.assert_called_once_with(checksum_path)
        mock_update_dir_md5_with_time.assert_has_calls(expected_calls)

    @patch('backup.os.path', autospec=True)
    @patch.object(backup, 'load_md5', spec=backup.load_md5)
    def test_update_dir_md5_with_time(self, mock_load_md5, mock_path):
        subj = Backup()
        logged = ['file-%s' % uid() for _ in uid_range()]  # файлы, которых нет в директории
        lost = ['file-%s' % uid() for _ in uid_range()]  # файлы, для которых нет сумм в журнале checksum
        less = ['file-%s' % uid() for _ in uid_range()]  # файлы с временем модификации < времени в log-е
        equal = ['file-%s' % uid() for _ in uid_range()]  # файлы с временем модификации == времени в log-е
        greater = ['file-%s' % uid() for _ in uid_range()]  # файлы с временем модификации > времени в log-е
        md5_sums = {f: uid() for f in lost + less + equal + greater}
        dir_md5_with_time = {f: (uid(), uid_time()) for f in logged + less + equal + greater}
        directory = 'directory-%s' % uid()

        def path(f):
            return directory + '/' + f

        def log_date_time(f):
            return dir_md5_with_time[f][1]

        getmtime = {path(f): log_date_time(f) - uid() for f in less}
        getmtime.update({path(f): log_date_time(f) for f in equal})
        getmtime.update({path(f): log_date_time(f) + uid() for f in greater})
        getmtime.update({path(f): uid_time() for f in lost})
        mock_path.getmtime.side_effect = lambda f: getmtime[f]
        name = 'file-%s' % uid()
        mock_load_md5.return_value = md5_sums
        files = lost + less + equal + greater + ['file-%s' % uid() for _ in uid_range()]  # + другие файлы
        expected = dir_md5_with_time.copy()
        expected.update({f: (md5_sums[f], getmtime[path(f)])
                         for f in lost + greater})

        subj.update_dir_md5_with_time(dir_md5_with_time, directory, name, files)

        self.assertEqual(dir_md5_with_time.keys() - expected.keys(), set())
        self.assertEqual(expected.keys() - dir_md5_with_time.keys(), set())
        diff = {f: (expected[f], dir_md5_with_time[f])
                for f in filter(lambda f: expected[f] != dir_md5_with_time[f], expected.keys())}
        self.assertEqual(diff, {})
        self.assertEqual(dir_md5_with_time, expected)

    @patch.object(Backup, 'sorted_md5_with_time_by_time', spec=Backup.sorted_md5_with_time_by_time)
    @patch.object(Backup, 'write_md5_with_time', spec=Backup.write_md5_with_time)
    @patch.object(backup, 'with_open', spec=backup.with_open)
    @patch.object(backup, 'md5sum', spec=backup.md5sum)
    @patch('backup.time', autospec=True)
    def test_slow_check_dir(self, mock_datetime, mock_md5sum, mock_with_open,
                            mock_write_md5_with_time, mock_sorted_md5_with_time_by_time):
        subj = Backup()
        keys = ['key-%s' % uid() for _ in uid_range()]
        mock_sorted_md5_with_time_by_time.return_value = keys
        md5_with_time = {k: (uid(), uid()) for k in keys}
        times = [uid_time() for _ in keys]
        mock_datetime.time.side_effect = times
        corrupted_index = uid(len(keys))
        mock_md5sum.side_effect = [uid() if i == corrupted_index else md5_with_time[keys[i]][0]
                                   for i in range(0, len(keys))]
        lines = ['line-%s' % uid() for _ in keys]
        mock_write_md5_with_time.side_effect = lines
        index = 0
        fd = ['fd-%s' % uid() for _ in keys]

        def md5_sum(i):
            return 'corrupted' if i == corrupted_index else md5_with_time[keys[i]][0]

        def with_open(file, mode, handler):
            nonlocal index
            mock_write_md5_with_time.assert_has_calls([call(fd[i], keys[i], md5_sum(i), times[i])
                                                       for i in range(0, index)])

            self.assertEqual(handler(fd[index]), lines[index])
            index += 1
            mock_write_md5_with_time.assert_has_calls([call(fd[i], keys[i], md5_sum(i), times[i])
                                                       for i in range(0, index)])

        mock_with_open.side_effect = with_open
        directory = 'directory-%s' % uid()
        checksum_path = 'checksum_path-%s' % uid()

        subj.slow_check_dir(directory, checksum_path, md5_with_time)

        mock_sorted_md5_with_time_by_time.assert_called_once_with(md5_with_time)
        mock_md5sum.assert_has_calls([call(directory + '/' + k, multiplier=subj.with_sleep_multiplier) for k in keys])
        mock_with_open.assert_has_calls([call(checksum_path, 'ab', mock.ANY) for _ in keys])

    @patch.object(Backup, 'sorted_md5_with_time_by_time', spec=Backup.sorted_md5_with_time_by_time)
    @patch.object(Backup, 'write_md5_with_time', spec=Backup.write_md5_with_time)
    def test_write_md5_with_time_dict(self, mock_write_md5_with_time, mock_sorted_md5_with_time_by_time):
        subj = Backup()
        fd = 'fd-%s' % uid()
        keys = ['key-%s' % uid() for _ in uid_range()]
        mock_sorted_md5_with_time_by_time.return_value = keys
        md5_with_time = {k: ('sum-%s' % uid(), 'time-%s' % uid()) for k in keys}

        subj.write_md5_with_time_dict(fd, md5_with_time)

        mock_sorted_md5_with_time_by_time.assert_called_once_with(md5_with_time)
        mock_write_md5_with_time.assert_has_calls([call(fd, k, md5_with_time[k][0], md5_with_time[k][1]) for k in keys])

    @patch.object(backup, 'time_to_string', spec=backup.time_to_string)
    def test_write_md5_with_time(self, mock_time_to_string):
        subj = Backup()
        fd = Mock(name='fd')
        key = 'key-%s' % uid()
        checksum = 'sum-%s' % uid()
        sum_time = uid_time()
        str_time = 'time-%s' % uid()
        mock_time_to_string.return_value = str_time

        subj.write_md5_with_time(fd, key, checksum, sum_time)

        fd.write.assert_called_once_with(bytes(checksum + ' ' + str_time + ' ' + key + '\n', 'UTF-8'))

    @patch("backup.time", autospec=True)
    def test_with_sleep_multiplier(self, mock_time):
        subj = Backup()
        self.assertEqual(subj.with_sleep_multiplier(), 4)
        mock_time.sleep.assert_called_once_with(0.01)

    def test_sorted_md5_with_time_by_time(self):
        subj = Backup()
        key1 = 'key1-%s' % uid()
        key2 = 'key2-%s' % uid()
        key3 = 'key3-%s' % uid()
        keys = [key3, key1, key2]
        md5_with_time = {k: (uid(), uid_time()) for k in keys}
        keys.reverse()

        self.assertEqual(subj.sorted_md5_with_time_by_time(md5_with_time), keys)

    @patch.object(Backup, 'lazy_write_md5', autospec=True)
    def test_lazy_write_md5_to_md5dirs(self, mock_lazy_write_md5):
        subj = Backup()
        md5dirs = ['dir-%s' % uid() for _ in uid_range()]
        key = 'key-%s' % uid()
        md5files = 'md5files-%s' % uid()
        expected_calls = [call(subj, d, key, md5files) for d in md5dirs]

        subj.lazy_write_md5_to_md5dirs(md5dirs, key, md5files)

        mock_lazy_write_md5.assert_has_calls(expected_calls)

    def test_copy(self):
        self.fail("TODO")

    @patch.object(backup, 'with_open', spec=backup.with_open)
    def test_do_copy(self, mock_with_open):
        for is_equals in (False, True):
            with self.subTest(is_equals=is_equals):
                subj = Backup()
                src = 'src-%s' % uid()
                data = [bytes('data-%s' % uid(), 'UTF-8') for _ in uid_range()] + [b'']
                md5 = hashlib.md5()
                for i in data:
                    md5.update(i)
                expected_checksum = md5.hexdigest().lower()
                illegal_checksum = 'checksum-%s' % uid()
                mock_in = Mock(name='mock_)in')
                mock_in.read.side_effect = data

                def with_open(name, mode, handler):
                    self.assertEqual((name, mode), (src, 'rb'))
                    return handler(mock_in)

                mock_with_open.side_effect = with_open
                mock_out = Mock(name='mock_out')
                expected_calls = [call(buf) for buf in data[:-1]]

                if is_equals:
                    subj.do_copy(mock_out, src, expected_checksum)
                else:
                    with self.assertRaises(IOError) as cm:
                        subj.do_copy(mock_out, src, illegal_checksum)
                    self.assertEqual(cm.exception.args[0], 'Corrupted [%s]. Checksum is %s but expected %s' %
                                     (src, expected_checksum, illegal_checksum))
                mock_out.write.assert_has_calls(expected_calls)

    def test_checksum(self):
        subj = Backup()
        dst = 'dst-%s' % uid()
        path = 'path-%s' % uid()

        md5, real = subj.checksum(dst, path)
        self.fail("TODO")

    def checksum_by_name(self):
        subj = Backup()
        directory = 'directory-%s' % uid()

        actual = subj.checksum_by_name(directory)
        self.fail("TODO")

    def checksum_by_dir(self):
        directory = 'directory-%s' % uid()

        actual = Backup.checksum_by_dir(directory)

        self.assertEqual(actual, directory + '/.checksum')

    @patch("backup.time", autospec=True)
    @patch("backup.log", autospec=True)
    def _test_full(self, mock_log, mock_time):
        now = uid_time()
        mock_time.time.return_value = now
        mock_log.debug = Mock()
        mock_log.info = Mock()
        mock_log.error = Mock()
        subj = Backup()
        self.assertEqual(time_to_iso(subj.checked), time_to_iso(now - 2 * 24 * 3600))

        self.fail("TODO")

    def test_time_to_string(self):
        t = 1660464293.984743
        self.assertEqual(backup.time_to_string(t), '2022-08-14T11:04:53.984743+03:00')

    def test_time_from_string(self):
        t = '2022-08-14T11:04:53.984743+03:00'
        self.assertEqual(backup.time_from_string(t), 1660464293.984743)


def uid_sequence():
    value = 0
    while True:
        value = value + 1
        yield value


uid_sequence_value = uid_sequence()


def uid(n=None):
    return next(uid_sequence_value) if n is None else next(uid_sequence_value) % n


def uid_time():
    return time.time() - uid() * 3600 * 24  # каждый вызов возвращает время на день раньше


def uid_range():
    return range(0, 2 + uid(3))


def time_to_iso(sec):
    s = time.strftime('%Y-%m-%dT%X%z', time.localtime(sec))
    micros = int((sec - int(sec)) * 1000000)
    return '%s.%06d%s:%s' % (s[0:-5], micros, s[-5:-2], s[-2:])
