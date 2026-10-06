import logging
import re

_TOKEN_PATH = re.compile(r"/(invite|password/reset)/[^/\s\"']+")


def _scrub(value):
    return _TOKEN_PATH.sub(r"/\1/<redacted>", value) if isinstance(value, str) else value


class RedactOneTimeLinks(logging.Filter):
    """Keep invitation and password-reset tokens out of log lines.

    Django logs the request path for 4xx and 5xx responses; for these two
    pages the path contains the one-time token.
    """

    def filter(self, record):
        record.msg = _scrub(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_scrub(arg) for arg in record.args)
        return True
