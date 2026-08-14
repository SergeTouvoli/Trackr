import unittest

from trackr import auth


class AuthTests(unittest.TestCase):
    def test_hash_et_verification_secret(self):
        salt_hex, hash_hex = auth.hash_secret("motdepasse")

        self.assertTrue(auth.verify_secret("motdepasse", salt_hex, hash_hex))
        self.assertFalse(auth.verify_secret("incorrect", salt_hex, hash_hex))

    def test_code_recuperation_format_humain(self):
        code = auth.generate_recovery_code()

        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")


if __name__ == "__main__":
    unittest.main()
