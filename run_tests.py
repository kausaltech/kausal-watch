#!/usr/bin/env python3
import importlib
import sys

import pytest

EXTENSIONS_PACKAGE_NAME = 'kausal_watch_extensions'

if __name__ == '__main__':
    args = [*sys.argv[1:], '.']
    if importlib.util.find_spec(EXTENSIONS_PACKAGE_NAME) is not None:
        args.append(EXTENSIONS_PACKAGE_NAME)
    raise SystemExit(pytest.main(args))
