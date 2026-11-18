import sys
import unittest
from pathlib import Path


def main() -> int:
    tests = Path(__file__).resolve().parent / 'tests'
    suite = unittest.defaultTestLoader.discover(str(tests), pattern='test_*.py')
    if suite.countTestCases() == 0:
        print('No regression tests were discovered.', file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
