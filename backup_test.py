import json
import logging
import math
import os.path
import time
from unittest import TestCase
from unittest import mock
from unittest.mock import Mock
from unittest.mock import MagicMock
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
        func = Mock()
        stop = uid_time()
        start = uid_time()
        mock_time.time.side_effect = [start, stop]
        func.side_effect = lambda:\
            mock_time.time.assert_called_once_with()

        backup.stop_watch(msg, func)

        mock_log.info.assert_called_once_with("[%s]: %1.3f sec", msg, stop - start)


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
                ('any', subj.help, False, False),
                (str(uid()), subj.help, False, False)):
            for empty in (False, True):
                with self.subTest(command=command, empty=empty):
                    mock_time_separator.reset_mock()
                    mock_svn_separator.reset_mock()
                    subj.commands = {}
                    src_dirs = ['src%s-%s' % (i, uid()) for i in range(0, 3)]
                    dest_dirs = ['dst%s-%s' % (i, uid()) for i in range(0, 3)]
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

    @patch("backup.time", autospec=True)
    @patch("backup.log", autospec=True)
    def test_full(self, mock_log, mock_time):
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


def uid():
    return next(uid_sequence_value)


def uid_time():
    return time.time() - uid() * 3600 * 24  # каждый вызов возвращает время на день раньше


def time_to_iso(t):
    return time.strftime("%Y-%m-%d %X", time.gmtime(t)) + ".%s" % (math.floor(t * 1000000 % 1000000))
