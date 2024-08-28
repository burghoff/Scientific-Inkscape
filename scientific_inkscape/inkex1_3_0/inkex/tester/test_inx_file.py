"""Check .inx file(s).

This is meant to be run an executable module, e.g.

    python -m inkex.tester.test_inx_file *.inx

"""
import argparse
import sys
import unittest
from typing import List

from .inx import InxMixin


class InxTestCase(InxMixin, unittest.TestCase):
    inx_files: List[str] = []

    def test_inx_file_parameters(self):
        for inx_file in self.inx_files:
            with self.subTest(inx_file=inx_file):
                self.assertInxIsGood(inx_file)

    def test_inx_file_schema(self):
        for inx_file in self.inx_files:
            with self.subTest(inx_file=inx_file):
                self.assertInxSchemaValid(inx_file)


def main(args=None):
    """Check .inx file(s)"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbosity",
        action="store_const",
        const=2,
        help="Verbose output",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        dest="verbosity",
        action="store_const",
        const=0,
        help="Quiet output",
    )
    parser.add_argument(
        "inx_files", metavar="INX-FILE", nargs="+", help="An .inx file to check"
    )
    args = parser.parse_args(args, namespace=argparse.Namespace(verbosity=1))

    InxTestCase.inx_files = args.inx_files
    runner = unittest.TextTestRunner(verbosity=args.verbosity)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InxTestCase)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
