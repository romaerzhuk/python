import json
import logging
import math
import os.path
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone
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
                file_time = uid()
                mock_path.isfile.return_value = is_file
                mock_path.getmtime.return_value = file_time
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
                    if is_file:
                        self.assertEqual(result, ({name1: sum1, name2: sum2, name3: sum3}, file_time))
                        mock_file.assert_called_once_with(path, encoding='UTF-8')
                    else:
                        self.assertEqual(result, ({}, -1))
                        mock_file.assert_not_called()

    @patch('backup.os.path', autospec=True)
    @patch.object(backup, 'with_open', spec=backup.with_open)
    def test_load_md5_with_times(self, mock_with_open, mock_path):
        for is_file in (False, True):
            with self.subTest(is_file=is_file):
                mock_with_open.reset_mock()
                mock_path.reset_mock()
                mock_path.isfile.return_value = is_file
                path = 'path-%s' % uid()

                def uid_spaces():
                    return ' ' * (1 + uid(3)) + '\t' * (uid(3))

                expected = {'name-%s' % uid(): ('sum-%s' % uid(), uid_datetime()) for _ in uid_range()}
                data = [expected[key][0] + uid_spaces() + expected[key][1].isoformat() + uid_spaces() + key
                        for key in expected]
                data.insert(1, 'sum-%s no matched value name-%s' % (uid(), uid()))
                data.insert(1, 'sum-%s 2021-99-99T99:99:99.123456+00:00 name-%s' % (uid(), uid()))  # illegal time

                def with_open(name, mode, read):
                    self.assertEqual((name, mode), (path, 'r'))
                    return read(data)

                mock_with_open.side_effect = with_open

                self.assertEqual(backup.load_md5_with_times(path), {} if not is_file else expected)

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


class BackupTest(TestCase):

    @patch("backup.time", autospec=True)
    def test_init(self, mock_time):
        now = uid_time()
        mock_time.time.return_value = now
        subj = Backup()

        self.assertEqual(time_to_iso(subj.checked), time_to_iso(now - 2 * 24 * 3600))

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
                        num if command == 'full' or command == 'clone' else None)
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

    @patch.object(Backup, 'check_dir', autospec=True)
    @patch.object(backup, 'with_lock_file', spec=backup.with_lock_file)
    def test_checks(self, mock_with_lock_file, mock_check_dir):
        subj = Backup()
        dirs = ['dir-%s' % uid() for _ in uid_range()]
        subj.dest_dirs = dirs
        index = 0

        def with_lock_file(path, handler):
            nonlocal index
            if index == 0:
                mock_check_dir.assert_not_called()
            else:
                mock_check_dir.assert_has_calls([call(subj, i) for i in dirs[0:index]])
            self.assertEqual(path, dirs[index] + '/.lock')

            handler()
            index += 1
            mock_check_dir.assert_has_calls([call(subj, i) for i in dirs[0:index]])

        mock_with_lock_file.side_effect = with_lock_file
        subj.checks()
        mock_with_lock_file.assert_has_calls([call(i + '/.lock', mock.ANY) for i in dirs])

    @patch.object(Backup, 'read_md5_with_times', spec=Backup.read_md5_with_times)
    @patch.object(Backup, 'safe_write', autospec=True)
    @patch.object(Backup, 'write_md5_with_time_dict', spec=Backup.write_md5_with_time_dict)
    @patch.object(Backup, 'slow_check_dir', spec=Backup.slow_check_dir)
    def test_check_dir(self, mock_slow_check_dir, mock_write_md5_with_time_dict,
                       mock_safe_write, mock_read_md5_with_times):
        for is_safe_write in (False, True):
            for m in (mock_slow_check_dir, mock_write_md5_with_time_dict,
                      mock_safe_write, mock_read_md5_with_times):
                m.reset_mock()
            with self.subTest(is_safe_write=is_safe_write):
                subj = Backup()
                path = 'path-%s' % uid()
                md5_with_time = uid()
                mock_read_md5_with_times.return_value = md5_with_time

                def safe_write(slf, file, write, name):
                    mock_write_md5_with_time_dict.assert_not_called()
                    self.assertEqual((slf, file, name()), (subj, '%s/.log' % path, 'create %s/.log' % path))
                    fd = uid()

                    write(fd)
                    mock_write_md5_with_time_dict.assert_called_once_with(fd, md5_with_time)
                    return is_safe_write

                mock_safe_write.side_effect = safe_write

                subj.check_dir(path)

                mock_read_md5_with_times.assert_called_once_with(path)
                mock_safe_write.assert_called_once_with(subj, path + '/.log', mock.ANY, mock.ANY)
                if is_safe_write:
                    mock_slow_check_dir.assert_called_once_with(path, md5_with_time)
                else:
                    mock_slow_check_dir.assert_not_called()

    @patch('backup.os', autospec=True)
    @patch.object(backup, 'load_md5_with_times', spec=backup.load_md5_with_times)
    @patch.object(Backup, 'read_dir_md5_with_time', spec=Backup.read_dir_md5_with_time)
    def test_read_md5_with_times(self, mock_read_dir_md5_with_time, mock_load_md5_with_times, mock_os):
        subj = Backup()
        directory = 'dir-%s' % uid()
        log_md5_with_time = uid()
        mock_load_md5_with_times.return_value = log_md5_with_time
        walk = [('root-%s' % uid(), 'dirs-%s' % uid(), ['file-%s' % uid() for _ in uid_range()])
                for _ in uid_range()]
        mock_os.walk.return_value = walk
        dir_md5_with_time = [{'key-%s' % uid(): 'value-%s' % uid() for _ in range(0, 3 + uid(5))}
                             for _ in range(0, len(walk))]
        mock_read_dir_md5_with_time.side_effect = dir_md5_with_time
        expected = {}
        for i in dir_md5_with_time:
            expected.update(i)
        expected_calls = [call(directory, root, set(files), log_md5_with_time) for root, dirs, files in walk]

        self.assertEqual(subj.read_md5_with_times(directory), expected)

        mock_load_md5_with_times.assert_called_once_with(directory + '/.log')
        mock_os.walk.assert_called_once_with(directory)
        mock_read_dir_md5_with_time.assert_has_calls(expected_calls)

    @patch.object(Backup, 'update_dir_md5_with_time', spec=Backup.update_dir_md5_with_time)
    def test_read_dir_md5_with_time(self, mock_update_dir_md5_with_time):
        subj = Backup()
        backup_dir = 'backup-%s' % uid()
        prefix = 'prefix-%s' % uid()
        directory = backup_dir + '/' + prefix
        targets = ['file-%s' % uid() for _ in uid_range()]  # целевые файлы
        files = targets + ['file-%s' % uid() for _ in uid_range()]  # + другие файлы в каталоге
        dir_md5_with_time = {prefix + '/' + f: uid() for f in targets}  # целевой результат
        log_md5_with_time = dir_md5_with_time.copy()
        log_md5_with_time.update({f: uid() for f in [  # файлы в других директориях игнорируются
            'dir-%s/file-%s' % (uid(), uid()) for _ in uid_range()]})
        log_md5_with_time.update({prefix + '/file-%s' % uid(): uid()
                                  for _ in uid_range()})   # файлы с этой директории, которых уже нет игнорируются
        expected = uid()
        mock_update_dir_md5_with_time.return_value = expected

        self.assertEquals(subj.read_dir_md5_with_time(backup_dir, directory, files, log_md5_with_time), expected)

        mock_update_dir_md5_with_time.assert_called_once_with(dir_md5_with_time, directory, files)

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


def uid_datetime():
    return datetime.now(tz=timezone.utc) - timedelta(hours=uid())


def uid_range():
    return range(0, 3 + uid(5))


def time_to_iso(t):
    return time.strftime("%Y-%m-%d %X", time.gmtime(t)) + ".%s" % (math.floor(t * 1000000 % 1000000))
