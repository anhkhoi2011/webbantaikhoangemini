import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_config import with_runtime_secrets, separate_runtime_secrets


class RuntimeConfigTests(unittest.TestCase):
    def test_private_file_overrides_public_placeholders(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "runtime_secrets.json").write_text(json.dumps({"payment": {"accessKey": "private-test-access", "secretKey": "private-test-secret"}}))
            cfg = with_runtime_secrets("payment_config.json", {"packagePrice": 129000, "accessKey": ""}, folder)
            self.assertEqual(cfg["accessKey"], "private-test-access")
            self.assertEqual(cfg["packagePrice"], 129000)

    def test_saving_credentials_keeps_them_out_of_public_config(self):
        with tempfile.TemporaryDirectory() as folder:
            public = separate_runtime_secrets("payment_config.json", {"accessKey": "new-test-access", "secretKey": "new-test-secret", "bankCode": "BIDV"}, folder)
            self.assertEqual(public["accessKey"], "")
            self.assertEqual(public["secretKey"], "")
            self.assertEqual(public["bankCode"], "BIDV")
            private = json.loads(Path(folder, "runtime_secrets.json").read_text())
            self.assertEqual(private["payment"]["secretKey"], "new-test-secret")
            separate_runtime_secrets("payment_config.json", {"secretKey": "", "packagePrice": 139000}, folder)
            self.assertEqual(with_runtime_secrets("payment_config.json", {}, folder)["secretKey"], "new-test-secret")

    def test_environment_can_provision_an_empty_server(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APIPAY_ACCESS_KEY": "env-test-access", "APIPAY_SECRET_KEY": "env-test-secret", "TELEGRAM_BOT_TOKEN": "env-test-token"}):
            cfg = with_runtime_secrets("payment_config.json", {}, folder)
            self.assertEqual(cfg["accessKey"], "env-test-access")
            self.assertEqual(cfg["secretKey"], "env-test-secret")
            self.assertEqual(with_runtime_secrets("telegram_config.json", {}, folder)["botToken"], "env-test-token")

if __name__ == "__main__":
    unittest.main()
