from __future__ import annotations

import unittest

from mia_exp.benchmarks.registry import iter_benchmarks, validate_data


class RegistryTests(unittest.TestCase):
    def test_all_spp_data_is_present_and_checksum_verified(self) -> None:
        specs = list(iter_benchmarks("spp"))
        self.assertEqual(len(specs), 4)

        reports = [validate_data(spec) for spec in specs]

        self.assertTrue(all(report["ok"] for report in reports), reports)
        self.assertEqual(
            [report["items"] for report in reports],
            [200, 100, 100, 50],
        )


if __name__ == "__main__":
    unittest.main()
