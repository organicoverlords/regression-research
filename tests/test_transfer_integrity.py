import tempfile
import unittest
from pathlib import Path

from tools.transfer_integrity import SCHEMA, build_receipt, validate_receipt, verify_file


class TransferIntegrityTests(unittest.TestCase):
    def test_matching_copy_is_proven(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bin"
            received = root / "received.bin"
            source.write_bytes(b"transfer-proof\x00\xff")
            received.write_bytes(source.read_bytes())
            receipt = build_receipt(source)
            result = verify_file(received, receipt)
            self.assertEqual(result["status"], "PROVEN")
            self.assertTrue(result["size_match"])
            self.assertTrue(result["sha256_match"])

    def test_same_size_corruption_is_rejected_by_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "a.bin"
            received = root / "b.bin"
            source.write_bytes(b"abcd")
            received.write_bytes(b"abce")
            result = verify_file(received, build_receipt(source))
            self.assertEqual(result["status"], "REJECTED")
            self.assertTrue(result["size_match"])
            self.assertFalse(result["sha256_match"])

    def test_missing_destination_is_explicit(self):
        receipt = {"schema": SCHEMA, "filename": "x.bin", "bytes": 1, "sha256": "0" * 64}
        result = verify_file(Path("definitely-missing-transfer-file"), receipt)
        self.assertEqual(result["reason"], "destination_missing")

    def test_malformed_receipt_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_receipt({"schema": SCHEMA, "bytes": 1, "sha256": "xyz"})


if __name__ == "__main__":
    unittest.main()
