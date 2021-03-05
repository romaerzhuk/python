import os.path
import unittest.mock
from unittest.mock import patch

from backup import Backup
from backup import SvnBackup


class SvnBackupTest(unittest.TestCase):

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


def sequence():
    value = 0
    while True:
        value = value + 1
        yield value


sequence_value = sequence()


def uid():
    return next(sequence_value)
