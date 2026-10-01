import unittest

import tdr_checker
import tdr_parser


class ParserImportTests(unittest.TestCase):
    def test_version_parsers_are_importable_from_main_module(self):
        for name in [
            "parse_line_v3",
            "parse_area_v4",
            "parse_point_v5",
            "parse_area_v6",
        ]:
            self.assertTrue(hasattr(tdr_checker, name))
            self.assertIs(getattr(tdr_checker, name), getattr(tdr_parser, name))

    def test_parser_module_still_exports_version_helpers(self):
        self.assertTrue(callable(tdr_parser.safe_read_utf))
        self.assertTrue(callable(tdr_parser.read_int_be))
        self.assertTrue(callable(tdr_parser.skip_v6_geometry))


if __name__ == "__main__":
    unittest.main()
