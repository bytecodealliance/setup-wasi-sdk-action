import io
import logging
import unittest

from action.logging import GitHubActionsHandler


class GitHubActionsHandlerTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.handler = GitHubActionsHandler(self.output)
        self.handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        self.logger = logging.Logger('test')
        self.logger.addHandler(self.handler)

    def test_emits_warning_workflow_command(self):
        self.logger.warning('retrying')

        self.assertEqual(self.output.getvalue(), '::warning::test: retrying\n')

    def test_emits_error_workflow_command(self):
        self.logger.error('giving up')

        self.assertEqual(self.output.getvalue(), '::error::test: giving up\n')

    def test_escapes_workflow_command_data(self):
        self.logger.warning('100%\r\nretry')

        self.assertEqual(
            self.output.getvalue(), '::warning::test: 100%25%0D%0Aretry\n')

    def test_emits_info_as_plain_log_output(self):
        self.logger.info('downloading')

        self.assertEqual(self.output.getvalue(), 'test: downloading\n')


if __name__ == '__main__':
    unittest.main()
