from __future__ import annotations

import unittest

from security import is_admin_authenticated


class SecurityTests(unittest.TestCase):
    def test_admin_without_configured_password_cannot_edit(self) -> None:
        self.assertFalse(is_admin_authenticated(None, "anything"))
        self.assertFalse(is_admin_authenticated("", "anything"))

    def test_admin_requires_exact_password(self) -> None:
        self.assertTrue(is_admin_authenticated("secret", "secret"))
        self.assertFalse(is_admin_authenticated("secret", "wrong"))


if __name__ == "__main__":
    unittest.main()
