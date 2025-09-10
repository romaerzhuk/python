import hashlib
import json
import logging
import os.path
import time
from unittest import TestCase
from unittest import mock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import call
from unittest.mock import patch
from typing import Tuple

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
                data = '%s  *%s\n' \
                       'any%s\n' \
                       '%s \t *%s\n' \
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

                def uid_spaces() -> str:
                    return ' ' * (1 + uid(3)) + '\t' * (uid(3))

                def uid_sum(width: int) -> str:
                    return ('sum-%s' % uid()).rjust(32 + width, '0')

                expected = {'name-%s' % uid(): (uid_sum(0), int(uid_time()))
                            for _ in uid_range()}
                keys = list(expected.keys())
                data = [expected[key][0] + uid_spaces() + time_to_iso(expected[key][1]) + uid_spaces() + key
                        for key in expected]
                data.append('%s no matched value name-%s' % (uid_sum(0), uid()))
                data.append('%s 2021-99-99T99:99:99.123456+00:00 name-%s' % (uid_sum(0), uid()))  # illegal time
                data.append(uid_sum(1) + uid_spaces() + time_to_iso(uid_time() - 1) + uid_spaces() + keys[0]) # некорректная сумма игнорируется
                data.append(uid_sum(1) + uid_spaces() + time_to_iso(uid_time() + 1) + uid_spaces() + keys[0]) # некорректная сумма игнорируется
                data.append(uid_sum(-1) + uid_spaces() + time_to_iso(uid_time() - 1) + uid_spaces() + keys[1]) # некорректная сумма игнорируется
                data.append(uid_sum(-1) + uid_spaces() + time_to_iso(uid_time() + 1) + uid_spaces() + keys[1]) # некорректная сумма игнорируется
                for i in range(30, 35):
                    if i != 32:
                        sum_time = int(uid_time())
                        key = 'name-%s' % uid()
                        data.append(('sum-%s' % uid()).rjust(i, '0') + ' ' + time_to_iso(sum_time) + ' '+ key)
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
        file_dict = {'file-%s' % uid(): uid() for _ in uid_range()}
        recovery = ['recovery-%s' % uid() for _ in uid_range()]
        indexes = [uid() for _ in uid_range()]
        lists = {i: ['list-%s' % uid() for _ in uid_range()] for i in indexes}

        subj.recovery_key_search(dst, key, name, md5dirs, file_dict, recovery, lists)

        self.fail("TODO")

    @patch.object(Backup, 'slow_check_dirs', autospec=True)
    @patch.object(backup, 'with_lock_file', spec=backup.with_lock_file)
    def test_checks(self, mock_with_lock_file, mock_slow_check_dirs):
        subj = Backup()
        dirs = ['dir-%s' % uid() for _ in uid_range()]
        subj.dest_dirs = dirs

        def with_lock_file(path, handler):
            mock_slow_check_dirs.assert_not_called()
            self.assertEqual(path, dirs[0] + '/.lock')

            handler()
            mock_slow_check_dirs.assert_called_once_with(subj)

        mock_with_lock_file.side_effect = with_lock_file

        subj.checks()

        mock_with_lock_file.assert_called_once_with(dirs[0] + '/.lock', mock.ANY)

    @patch.object(Backup, 'read_dir_md5_with_time', spec=Backup.read_dir_md5_with_time)
    @patch.object(Backup, 'checksum_path', spec=Backup.checksum_path)
    @patch('backup.os', autospec=True)
    def test_read_directory_md5_with_time(self, mock_os, mock_checksum_path, mock_read_dir_md5_with_time):
        subj = Backup()
        for is_empty in (False, True):
            for m in (mock_os, mock_checksum_path, mock_read_dir_md5_with_time):
                m.reset_mock()
            with self.subTest(is_empty=is_empty):
                root = 'root-%s' % uid()
                files = ['file-%s' % uid() in uid_range()]
                mock_os.walk.return_value = [] if is_empty \
                    else [(root, 'dirs-%s' % uid(), files)] + \
                         [('root-%s' % uid(), 'dirs-%s' % uid(), ['file-%s' % uid() in uid_range()])]
                directory = 'directory-%s' % uid()
                checksum_path = 'checksum_path-%s' % uid()
                mock_checksum_path.return_value = checksum_path
                expected = {} if is_empty else 'result-%s' % uid()
                mock_read_dir_md5_with_time.return_value = expected

                actual = subj.read_directory_md5_with_time(directory)

                self.assertEqual(actual, expected)
                mock_os.walk.assert_called_once_with(directory)
                mock_checksum_path.assert_has_calls([] if is_empty else [call(directory)])
                mock_read_dir_md5_with_time.assert_has_calls([] if is_empty
                                                             else [call(directory, checksum_path, set(files))])

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
                                  for _ in uid_range()})  # файлы, которых уже нет, игнорируются
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

    @patch.object(Backup, 'slow_check_dir', autospec=True)
    @patch.object(Backup, 'sorted_dirs', autospec=True)
    def test_slow_check_dirs(self, mock_sorted_dirs, mock_slow_check_dir):
        subj = Backup()
        dirs = ['dir-%s' % uid() for _ in uid_range()]
        mock_sorted_dirs.return_value = dirs

        subj.slow_check_dirs()

        mock_slow_check_dir.assert_has_calls([call(subj, d) for d in dirs])

    @patch.object(Backup, 'time_by_directory', spec=Backup.time_by_directory)
    def test_sorted_dirs(self, mock_time_by_directory):
        subj = Backup()
        dest_dirs = ['dest_dir-%s' % uid(), 'dest_dir-%s' % uid()]
        subj.dest_dirs = dest_dirs
        dirs = ['dir-%s' % uid() for _ in range(0, 4)]
        times = [uid_time() for _ in range(0, len(dirs))]
        time_by_dir = {dest_dirs[0]: {dirs[0]: times[1], dirs[1]: times[3]},
                       dest_dirs[1]: {dirs[2]: times[0], dirs[3]: times[2]}}
        mock_time_by_directory.side_effect = lambda d: time_by_dir[d]
        expected = [dirs[1], dirs[3], dirs[0], dirs[2]]

        actual = subj.sorted_dirs()

        self.assertEqual(actual, expected)
        mock_time_by_directory.assert_has_calls([call(d) for d in dest_dirs])

    @patch.object(Backup, 'safe_append_checksum', autospec=True)
    @patch.object(backup, 'md5sum', spec=backup.md5sum)
    @patch('backup.time', autospec=True)
    @patch.object(Backup, 'sorted_name_with_checksum', spec=Backup.sorted_name_with_checksum)
    @patch.object(Backup, 'rewrite_dir_checksums', autospec=True)
    def test_slow_check_dir(self, mock_rewrite_dir_checksums, mock_sorted_name_with_checksum_by_time,
                            mock_time, mock_md5sum, mock_safe_append_checksum):
        subj = Backup()
        dir_checksums = 'dir_checksums-%s' % uid()
        mock_rewrite_dir_checksums.return_value = dir_checksums
        name_with_checksums = [('name-%s' % uid(), 'checksum-%s' % uid()) for _ in uid_range()]
        mock_sorted_name_with_checksum_by_time.return_value = name_with_checksums
        times = [uid_time() for _ in name_with_checksums]
        mock_time.time.side_effect = times
        corrupted_index = uid(len(name_with_checksums))
        mock_md5sum.side_effect = ['checksum-%s' % uid() if i == corrupted_index else name_with_checksums[i][1]
                                   for i in range(0, len(name_with_checksums))]
        directory = 'dir-%s' % uid()

        subj.slow_check_dir(directory)

        mock_rewrite_dir_checksums.assert_called_once_with(subj, directory)
        mock_sorted_name_with_checksum_by_time.assert_called_once_with(dir_checksums)
        mock_md5sum.assert_has_calls([call(directory + '/' + name, multiplier=subj.with_sleep_multiplier)
                                      for name, _ in name_with_checksums])
        mock_safe_append_checksum.assert_has_calls([call(subj, directory, name_with_checksums[i][0],
                                                         'corrupted' if i == corrupted_index
                                                         else name_with_checksums[i][1],
                                                         times[i])
                                                    for i in range(0, len(name_with_checksums))])

    @patch.object(Backup, 'max_time', spec=Backup.max_time)
    @patch('backup.os', autospec=True)
    def test_time_by_directory(self, mock_os, mock_max_time):
        subj = Backup()
        roots = ['root-%s' % uid() for _ in uid_range()]
        empty_root = roots[uid(len(roots))]
        files_by_root = {root: [] if root == empty_root else ['file-%s' % uid() for _ in uid_range()] for root in roots}
        mock_os.walk.return_value = [(r, 'dirs-%s' % uid(), files_by_root[r]) for r in roots]
        time_by_root = {root: uid_time() for root in roots}
        mock_max_time.side_effect = lambda root, _: time_by_root[root]
        expected = {root: time_by_root[root] for root in filter(lambda root: root != empty_root, roots)}
        directory = 'directory-%s' % uid()

        actual = subj.time_by_directory(directory)

        self.assertEqual(actual, expected)
        mock_max_time.assert_has_calls([call(root, files_by_root[root])
                                        for root in filter(lambda root: root != empty_root, roots)])

    def test_sorted_name_with_checksum(self):
        subj = Backup()
        n = 3 + uid(5)
        name = ['name-%s' % uid() for _ in range(0, n)]
        checksum = ['checksum-%s' % uid() for _ in name]
        times = [uid_time() for _ in name]
        checksum_with_time_by_name = {name[i]: (checksum[i], times[i]) for i in range(0, n)}
        expected = [(name[i], checksum[i]) for i in range(0, n)]
        expected.reverse()

        actual = subj.sorted_name_with_checksum(checksum_with_time_by_name)

        self.assertEqual(actual, expected)

    @patch.object(Backup, 'write_md5_with_time_dict', spec=Backup.write_md5_with_time_dict)
    @patch.object(Backup, 'safe_write', autospec=True)
    @patch.object(backup, 'remove_file', spec=backup.remove_file)
    @patch.object(Backup, 'checksum_path', spec=Backup.checksum_path)
    @patch.object(Backup, 'read_directory_md5_with_time', spec=Backup.read_directory_md5_with_time)
    def test_rewrite_dir_checksums(self, mock_read_directory_md5_with_time, mock_checksum_path, mock_remove_file,
                                   mock_safe_write, mock_write_md5_with_time_dict):
        for md5_with_time_len in uid_range():
            for m in (mock_read_directory_md5_with_time, mock_checksum_path, mock_remove_file,
                      mock_safe_write, mock_write_md5_with_time_dict):
                m.reset_mock()
            with self.subTest(md5_with_time_len=md5_with_time_len):
                subj = Backup()
                expected = [uid() for _ in range(0, md5_with_time_len)]
                mock_read_directory_md5_with_time.return_value = expected
                checksum_path = 'checksum_path-%s' % uid()
                mock_checksum_path.return_value = checksum_path

                def safe_write(slf, file, write, name):
                    mock_write_md5_with_time_dict.assert_not_called()
                    self.assertEqual((slf, file, name()), (subj, checksum_path, 'update %s' % checksum_path))
                    fd = uid()

                    write(fd)
                    mock_write_md5_with_time_dict.assert_called_once_with(fd, expected)

                mock_safe_write.side_effect = safe_write
                directory = 'directory-%s' % uid()

                actual = subj.rewrite_dir_checksums(directory)

                self.assertEqual(actual, expected)
                mock_read_directory_md5_with_time.assert_called_once_with(directory)
                mock_checksum_path.assert_called_once_with(directory)
                mock_remove_file.assert_has_calls([] if md5_with_time_len > 0
                                                  else [call(checksum_path)])
                mock_safe_write.assert_has_calls([] if md5_with_time_len == 0
                                                 else [call(subj, checksum_path, mock.ANY, mock.ANY)])

    @patch('backup.os.path', autospec=True)
    def test_max_time(self, mock_os_path):
        subj = Backup()
        directory = 'dir-%s' % uid()
        files = ['file-%s' % uid() for _ in uid_range()]
        expected = uid_time()
        index = uid(len(files))
        times = {directory + '/' + files[i]: uid_time() if i != index else expected for i in range(0, len(files))}
        mock_os_path.getmtime.side_effect = lambda path: times[path]

        actual = subj.max_time(directory, files)

        self.assertEqual(actual, expected)
        mock_os_path.getmtime.assert_has_calls([call(directory + '/' + f) for f in files])

    @patch.object(Backup, 'error', autospec=True)
    @patch.object(Backup, 'append_checksum', spec=Backup.append_checksum)
    def test_safe_append_checksum(self, mock_append_checksum, mock_error):
        for raised in (None, BaseException(), Exception()):
            with self.subTest(raised=raised):
                mock_append_checksum.reset_mock()
                mock_error.reset_mock()
                subj = Backup()
                directory = 'directory-%s' % uid()
                name = 'name-%s' % uid()
                checksum = 'checksum-%s' % uid()
                sum_time = uid_time()

                def append_checksum(_directory, _name, _checksum, _sum_time):
                    if raised is not None:
                        raise raised

                mock_append_checksum.side_effect = append_checksum

                subj.safe_append_checksum(directory, name, checksum, sum_time)

                mock_append_checksum.assert_called_once_with(directory, name, checksum, sum_time)
                mock_error.assert_has_calls([] if raised is None
                                            else [call(subj, 'append checksum error: %s', raised)])

    @patch.object(Backup, 'write_md5_with_time', spec=Backup.write_md5_with_time)
    @patch.object(Backup, 'checksum_path', spec=Backup.checksum_path)
    @patch.object(backup, 'with_open', spec=backup.with_open)
    def test_append_checksum(self, mock_with_open, mock_checksum_path, mock_write_md5_with_time):
        subj = Backup()
        name = 'name-%s' % uid()
        checksum = 'checksum-%s' % uid()
        sum_time = uid_time()

        def with_open(_file, _mode, handler):
            mock_write_md5_with_time.assert_not_called()
            fd = 'fd-%s' % uid()
            handler(fd)
            mock_write_md5_with_time.assert_called_once_with(fd, name, checksum, sum_time)

        mock_with_open.side_effect = with_open
        checksum_path = 'checksum_path-%s' % uid()
        mock_checksum_path.return_value = checksum_path
        directory = 'dir-%s' % uid()

        subj.append_checksum(directory, name, checksum, sum_time)

        mock_with_open.assert_called_once_with(checksum_path, 'ab', mock.ANY)
        mock_checksum_path.assert_called_once_with(directory)

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

        actual = subj.sorted_md5_with_time_by_time(md5_with_time)

        self.assertEqual(actual, keys)

    @patch.object(Backup, 'lazy_write_md5', autospec=True)
    def test_lazy_write_md5_to_md5dirs(self, mock_lazy_write_md5):
        subj = Backup()
        md5dirs = ['dir-%s' % uid() for _ in uid_range()]
        key = 'key-%s' % uid()
        md5files = 'md5files-%s' % uid()
        expected_calls = [call(subj, d, key, md5files) for d in md5dirs]

        subj.lazy_write_md5_to_md5dirs(md5dirs, key, md5files)

        mock_lazy_write_md5.assert_has_calls(expected_calls)

    @patch.object(Backup, 'safe_write', autospec=True)
    @patch.object(Backup, 'do_copy', autospec=True)
    @patch('backup.StopWatch', autospec=True)
    def test_copy(self, mock_stop_watch, mock_do_copy, mock_safe_write):
        for contains in (False, True):
            for is_safe_write in (False, True):
                for m in (mock_stop_watch, mock_safe_write, mock_do_copy):
                    m.reset_mock()
                with self.subTest(contains=contains, is_safe_write=is_safe_write):
                    mock_sw = Mock(name='mock_sw')
                    mock_stop_watch.return_value = mock_sw
                    mock_do_copy.side_effect = lambda x, y, z: None
                    src_dir = 'src_dir-%s' % uid()
                    dest_dir = 'dest_dir-%s' % uid()
                    rec = Mock(name='rec')
                    rec.dir = src_dir if contains else 'rec_dir-%s' % uid()
                    checksum = 'checksum-%s' % uid()
                    rec_md5 = {'dir-%s' % uid(): 'checksum-%s' % uid() for _ in uid_range()}
                    rec_md5[src_dir] = checksum
                    rec.md5 = rec_md5
                    rec.list = ['dir-%s' % uid() for _ in uid_range()] + ([src_dir] if contains else []) + \
                               ['dir-%s' % uid() for _ in uid_range()]
                    expected_rec_md5 = rec_md5.copy()
                    if is_safe_write:
                        expected_rec_md5[dest_dir] = checksum
                    subj = Backup()
                    subj.dest_dirs = [src_dir] + ['dir-%s' % uid() for _ in uid_range()]
                    key = '/key-%s' % uid()
                    mock_out = Mock(name='out')

                    def safe_write(_self, dst, do_copy, name):
                        expected_name = 'cp %s%s %s' % (src_dir, key, dst)
                        mock_stop_watch.assert_called_once_with(expected_name)
                        self.assertEqual(name(), expected_name)
                        mock_do_copy.assert_not_called()

                        do_copy(mock_out)

                        mock_do_copy.assert_called_once_with(mock_out, src_dir + key, checksum)
                        mock_sw.assert_not_called()
                        return is_safe_write

                    mock_safe_write.side_effect = safe_write

                    subj.copy(rec, dest_dir, key)

                    self.assertEqual(rec.md5, expected_rec_md5)
                    mock_safe_write.assert_called_once_with(subj, dest_dir + key, mock.ANY, mock.ANY)
                    mock_sw.stop.assert_called_once_with()

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
                mock_in = Mock(name='mock_in')
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

    @patch.object(Backup, 'safe_append_checksum', autospec=True)
    @patch.object(Backup, 'safe_md5sum', autospec=True)
    @patch.object(Backup, 'checksum_by_name', autospec=True)
    @patch('backup.os.path', autospec=True)
    def test_checksum(self, mock_os_path, mock_checksum_by_name, mock_safe_md5sum, mock_safe_append_checksum):
        for contains in (False, True):
            for offset in (None, -5, -2, -1, 0, 1, 2, 5):
                for is_equals in (False, True):
                    for m in (mock_os_path, mock_checksum_by_name, mock_safe_md5sum, mock_safe_append_checksum):
                        m.reset_mock()
                    with self.subTest(contains=contains, offset=offset, is_equals=is_equals):
                        subj = Backup()
                        subj.checked = uid_time()
                        directory = 'dir-%s' % uid()
                        mock_os_path.dirname.return_value = directory
                        name = 'name-%s' % uid()
                        mock_os_path.basename.return_value = name
                        checksum_by_name = {'name-%s' % uid(): uid() for _ in uid_range()}
                        checksum = 'checksum-%s' % uid()
                        if contains:
                            checksum_by_name[name] = (checksum, None if offset is None else subj.checked + offset)
                        mock_checksum_by_name.return_value = checksum_by_name
                        mock_safe_md5sum.return_value = checksum if is_equals else 'checksum-%s' % uid()
                        path = 'path-%s' % uid()
                        expected_checksum_by_name = checksum_by_name.copy()
                        expected = (None, False)
                        if contains:
                            if offset is None or offset > 0:
                                expected = (checksum, False)
                            else:
                                expected = (checksum if is_equals else None, is_equals)
                                expected_checksum_by_name[name] = (checksum if is_equals else None, None)

                        actual = subj.checksum(path)

                        self.assertEqual(actual, expected)
                        self.assertEqual(checksum_by_name, expected_checksum_by_name)
                        mock_os_path.dirname.assert_called_once_with(path)
                        mock_os_path.basename.assert_called_once_with(path)
                        mock_safe_md5sum.assert_has_calls([call(subj, path)]
                                                          if contains and offset is not None and offset < 0 else [])

    @patch.object(Backup, 'error', autospec=True)
    @patch('backup.md5sum', autospec=True)
    def test_safe_md5sum(self, mock_md5sum, mock_error):
        for raised in (None, BaseException(), Exception()):
            with self.subTest(raised=raised):
                mock_md5sum.reset_mock()
                mock_error.reset_mock()
                subj = Backup()
                path = 'path-%s' % uid()
                checksum = 'checksum-%s' % uid()

                # noinspection PyUnusedLocal
                def md5sum(_path, is_stop_watch):
                    if raised is None:
                        return checksum
                    raise raised

                mock_md5sum.side_effect = md5sum
                expected = checksum if raised is None else None

                actual = subj.safe_md5sum(path)

                self.assertEqual(actual, expected)
                mock_md5sum.assert_has_calls([] if raised is None else [call(path, is_stop_watch=False)])
                mock_error.assert_has_calls([] if raised is None
                                            else [call(subj, 'md5sum error: %s', raised)])

    @patch.object(Backup, 'read_directory_md5_with_time', spec=Backup.read_directory_md5_with_time)
    def test_checksum_by_name(self, mock_read_directory_md5_with_time):
        for contains in (False, True):
            with self.subTest(is_equals=contains):
                subj = Backup()
                subj.checksums_by_dir = {'dir-%s' % uid(): uid() for _ in uid_range()}
                expected_checksums_by_dir = subj.checksums_by_dir.copy()
                directory = 'dir-%s' % uid()
                expected_checksum_by_name = 'expected_checksum_by_name-%s' % uid()
                expected_checksums_by_dir[directory] = expected_checksum_by_name
                if contains:
                    subj.checksums_by_dir[directory] = expected_checksum_by_name
                mock_read_directory_md5_with_time.return_value = expected_checksum_by_name

                actual = subj.checksum_by_name(directory)

                self.assertEqual(actual, expected_checksum_by_name)
                self.assertEqual(subj.checksums_by_dir, expected_checksums_by_dir)
                mock_read_directory_md5_with_time.assert_has_calls([] if contains else [call(directory)])

    def test_checksum_path(self):
        directory = 'directory-%s' % uid()

        actual = Backup.checksum_path(directory)

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
