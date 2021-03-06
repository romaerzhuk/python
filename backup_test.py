import json
import math
import os.path
import time
import logging
from unittest import TestCase
from unittest import mock
from unittest.mock import Mock
from unittest.mock import patch

from backup import Backup
from backup import SvnBackup


class SvnBackupTest(TestCase):

    @patch('backup.system', autospec=True)
    def test_svn_revision(self, mock_system):
        backup = Backup()
        subj = SvnBackup(backup)
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
        backup = Backup()

        self.assertEqual(time_to_iso(backup.checked), time_to_iso(now - 2 * 24 * 3600))

    @patch("backup.sys", autospec=True)
    @patch("backup.log", autospec=True)
    @patch.object(Backup, "read_config", spec=Backup.read_config)
    def test_configure(self, mock_read_config, mock_log, mock_sys):
        for log_level in (None, logging.DEBUG, logging.INFO, logging.ERROR):
            for log_format in (None, str(uid())):
                with self.subTest(log_level=log_level, log_format=log_format):
                    backup = Backup()
                    mock_log.reset_mock()
                    mock_sys.reset_mock()
                    config = {}
                    mock_read_config.return_value = config
                    if log_format is not None:
                        config['log_format'] = log_format
                    if log_level is not None:
                        config['log_level'] = logging.getLevelName(log_level)
                    mock_log.getLevelName.side_effect = logging.getLevelName

                    backup.configure()

                    mock_log.basicConfig.assert_called_once_with(
                        level=mock_log.INFO if log_level is None else log_level,
                        stream=mock_sys.stdout,
                        format="%(message)s" if log_format is None else log_format)
                    mock_sys.setrecursionlimit.assert_called_once_with(100)

    @patch('os.path', autospec=True)
    def test_read_config(self, mock_path):
        backup = Backup()
        path = str(uid())
        mock_path.expanduser.return_value = path
        config = {'a': uid(), 'b': uid()}
        data = json.dumps(config)
        with patch('builtins.open', new_callable=mock.mock_open, read_data=data) as mock_file:
            self.assertEqual(backup.read_config(), config)
        mock_file.assert_called_once_with(path, encoding='UTF-8')

    @patch("backup.time", autospec=True)
    @patch("backup.log", autospec=True)
    def _test_full(self, mock_log, mock_time):
        now = uid_time()
        mock_time.time.return_value = now
        mock_log.debug = Mock()
        mock_log.info = Mock()
        mock_log.error = Mock()
        backup = Backup()
        self.assertEqual(time_to_iso(backup.checked), time_to_iso(now - 2 * 24 * 3600))

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
