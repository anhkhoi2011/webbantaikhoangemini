import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import telegram_sender


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return json.dumps(self.payload).encode()


class TelegramDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = patch.object(server, "BASE_DIR", self.temp.name)
        self.base.start()
        self.addCleanup(self.base.stop)
        config_patch = patch.object(telegram_sender, "get_current_tele_config", return_value=("test-token", ["chat-a"]))
        self.config = config_patch.start()
        self.addCleanup(config_patch.stop)
        server.write_json_file("payment_config.json", {"googleSheetWebhookUrl": "https://example.invalid/sheet"})
        self.order = {"orderId": "#PAID-TEST", "status": "paid", "amountRaw": 129000, "amount": "129000"}
        server.write_json_file("orders.json", [self.order])

    def stored(self):
        return server.read_json_file("orders.json", [])[0]

    def test_health_failure_sends_local_once_then_retries_sheet_without_notification(self):
        with patch.object(server.urllib.request, "urlopen", side_effect=TimeoutError), patch.object(telegram_sender, "send_telegram_raw", return_value=True) as send:
            server.sync_order_integrations(self.order["orderId"])
            server.sync_order_integrations(self.order["orderId"])
            self.assertEqual(send.call_count, 1)
        self.assertTrue(self.stored()["paidNotified"])
        self.assertEqual(self.stored()["telegramOwner"], "server")
        self.assertIn("sheetSyncError", self.stored())
        with patch.object(server.urllib.request, "urlopen", side_effect=[Response({"protocolVersion": 2}), Response({"status": "success"})]) as opener:
            server.sync_order_integrations(self.order["orderId"])
            self.assertEqual(json.loads(opener.call_args.args[0].data)["action"], "sync_order")
        self.assertEqual(self.stored()["sheetSyncError"], "")

    def test_explicit_legacy_single_chat_failure_uses_fallback(self):
        responses = [Response({"protocolVersion": 2}), Response({"status": "success", "notificationsComplete": False})]
        with patch.object(server.urllib.request, "urlopen", side_effect=responses), patch.object(telegram_sender, "send_telegram_raw", return_value=True) as send:
            server.sync_order_integrations(self.order["orderId"])
        send.assert_called_once()
        self.assertTrue(self.stored()["paidNotified"])

    def test_partial_script_receipts_only_retry_missing_chat(self):
        self.config.return_value = ("test-token", ["chat-a", "chat-b"])
        responses = [Response({"protocolVersion": 2}), Response({"status": "success", "notificationsComplete": False, "telegramSent": {"chat-a": {"messageId": 10}}})]
        with patch.object(server.urllib.request, "urlopen", side_effect=responses), patch.object(telegram_sender, "send_telegram_raw", return_value=True) as send:
            server.sync_order_integrations(self.order["orderId"])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.kwargs["chat_id"], "chat-b")
        self.assertTrue(self.stored()["paidNotified"])

    def test_ambiguous_post_timeout_does_not_send_duplicate(self):
        with patch.object(server.urllib.request, "urlopen", side_effect=[Response({"protocolVersion": 2}), TimeoutError()]), patch.object(telegram_sender, "send_telegram_raw") as send:
            server.sync_order_integrations(self.order["orderId"])
        send.assert_not_called()
        self.assertNotIn("telegramOwner", self.stored())
        self.assertTrue(self.stored()["sheetSyncError"])

    def test_legacy_multiple_chats_without_receipts_retries_script(self):
        self.config.return_value = ("test-token", ["chat-a", "chat-b"])
        responses = [Response({"protocolVersion": 2}), Response({"status": "success", "notificationsComplete": False})]
        with patch.object(server.urllib.request, "urlopen", side_effect=responses), patch.object(telegram_sender, "send_telegram_raw") as send:
            server.sync_order_integrations(self.order["orderId"])
        send.assert_not_called()
        self.assertNotIn("paidNotified", self.stored())

    def test_failed_local_chat_retries_without_repeating_successful_chat(self):
        self.config.return_value = ("test-token", ["chat-a", "chat-b"])
        with patch.object(server.urllib.request, "urlopen", side_effect=TimeoutError), patch.object(telegram_sender, "send_telegram_raw", side_effect=[True, False, True]) as send:
            server.sync_order_integrations(self.order["orderId"])
            self.assertFalse(self.stored()["paidNotified"])
            self.assertTrue(self.stored()["telegramSyncError"])
            self.assertNotIn("telegramOwner", server.sheet_payload(self.stored()))
            self.assertNotIn("telegramSyncError", server.sheet_payload(self.stored()))
            server.sync_order_integrations(self.order["orderId"])
            self.assertEqual([call.kwargs["chat_id"] for call in send.call_args_list], ["chat-a", "chat-b", "chat-b"])
        self.assertTrue(self.stored()["paidNotified"])
        self.assertEqual(self.stored()["telegramSyncError"], "")

    def test_successful_script_confirmation_never_sends_local_alert(self):
        responses = [Response({"protocolVersion": 2}), Response({"status": "success", "notificationsComplete": True})] * 2
        with patch.object(server.urllib.request, "urlopen", side_effect=responses) as opener, patch.object(telegram_sender, "send_telegram_raw") as send:
            server.sync_order_integrations(self.order["orderId"])
            server.sync_order_integrations(self.order["orderId"])
            server.sync_order_integrations(self.order["orderId"])
        self.assertEqual(opener.call_count, 4)
        send.assert_not_called()
        self.assertTrue(self.stored()["paidNotified"])
        self.assertEqual(self.stored()["sheetSyncError"], "")

    def test_empty_recipient_list_is_not_delivery_success(self):
        self.config.return_value = ("test-token", [])
        server.write_json_file("payment_config.json", {})
        with patch.object(telegram_sender, "send_telegram_raw") as send:
            server.sync_order_integrations(self.order["orderId"])
        send.assert_not_called()
        self.assertFalse(self.stored()["paidNotified"])

    def test_pending_order_never_sends_local_alert(self):
        server.write_json_file("orders.json", [dict(self.order, status="pending")])
        with patch.object(server.urllib.request, "urlopen", side_effect=TimeoutError), patch.object(telegram_sender, "send_telegram_raw") as send:
            server.sync_order_integrations(self.order["orderId"])
        send.assert_not_called()

    def test_missing_token_fails_without_request(self):
        self.config.return_value = ("", ["chat-a"])
        with patch.object(telegram_sender.urllib.request, "urlopen") as opener, patch.object(sys, "stderr", io.StringIO()):
            self.assertFalse(telegram_sender.send_telegram_raw("test"))
        opener.assert_not_called()

    def test_telegram_failure_logs_description_without_token(self):
        failure = HTTPError("https://example.invalid", 403, "Forbidden", {}, io.BytesIO(b'{"description":"Forbidden: bot was kicked"}'))
        with patch.object(telegram_sender.urllib.request, "urlopen", side_effect=failure), patch.object(sys, "stderr", io.StringIO()) as output:
            self.assertFalse(telegram_sender.send_telegram_raw("test"))
        self.assertIn("bot was kicked", output.getvalue())
        self.assertNotIn("test-token", output.getvalue())


class TelegramConfigTests(unittest.TestCase):
    def test_environment_token_works_without_config_files(self):
        import os
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram_sender, "BASE_DIR", folder), patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "env-test-token"}):
            token, chats = telegram_sender.get_current_tele_config()
        self.assertEqual(token, "env-test-token")
        self.assertEqual(chats, [telegram_sender.DEFAULT_CHAT_ID])


if __name__ == "__main__":
    unittest.main()
