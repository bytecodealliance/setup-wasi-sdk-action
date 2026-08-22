"""Logging configuration for local use and GitHub Actions."""

import logging
import os
import sys


def _escape_workflow_command(message: str):
    """Escape data with special meaning in a GitHub workflow command."""
    return message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


class GitHubActionsHandler(logging.StreamHandler):
    """Emit warnings and errors as GitHub Actions workflow commands."""

    def emit(self, record):
        try:
            message = self.format(record)
            if record.levelno >= logging.ERROR:
                message = f'::error::{_escape_workflow_command(message)}'
            elif record.levelno >= logging.WARNING:
                message = f'::warning::{_escape_workflow_command(message)}'
            self.stream.write(message + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def configure_logging(verbose: bool, logger_name: str):
    """Configure logging for the current execution environment."""
    level = logging.DEBUG if verbose else logging.WARNING
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        handler = GitHubActionsHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        logging.basicConfig(level=level, handlers=[handler], force=True)
    else:
        logging.basicConfig(level=level, force=True)
    logging.getLogger().name = logger_name
