import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import apipay_bridge

class PaymentFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = patch.object(server, "BASE_DIR", self.temp.name)
        self.base.start()
        self.queue = patch.object(server, "queue_order_sync")
        self.queue.start()
        server.write_json_file("payment_config.json", {"packagePrice": 90000})
        server.write_json_file("licenses.json", [{"id": 1, "link": "https://example.invalid/license", "status": "Sẵn sàng", "assignedTo": "-"}])
        self.order = {"orderId": "#TEST-A", "memo": "PRO18T 0900000000 AABBCCDD", "phone": "0900000000", "name": "Test", "email": "test@example.invalid", "amountRaw": 90000, "amount": "90.000đ", "status": "Chờ thanh toán", "ip": "203.0.113.5", "utmSource": "facebook", "utmCampaign": "Campaign", "browser": "Safari", "fullUrl": "https://example.invalid/?utm_source=facebook"}
        server.write_json_file("orders.json", [self.order])
        server.write_json_file("bank_transactions.json", [])
        self.http = server.HTTPServer(("127.0.0.1", 0), server.GeminiCRMHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.queue.stop()
        self.base.stop()
        self.temp.cleanup()
    def post(self, path, data):
        req = Request(f"http://127.0.0.1:{self.http.server_port}{path}", data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as response:
            return json.load(response)
    def test_four_bank_deliveries_one_paid_order_one_license(self):
        for i in range(4):
            self.post("/api/webhook", {"data": {"id": f"delivery-{i}", "amount": 90000, "content": self.order["memo"], "status": "COMPLETED"}})
        orders = server.read_json_file("orders.json", [])
        self.assertEqual(len(orders), 1)
        self.assertTrue(server.is_paid_order(orders[0]))
        self.assertEqual(orders[0]["licenseLink"], "https://example.invalid/license")
        self.assertEqual(orders[0]["utmSource"], "facebook")
        self.assertEqual(len(server.read_json_file("bank_transactions.json", [])), 1)
        self.post("/api/orders", self.order)
        self.assertTrue(server.is_paid_order(server.read_json_file("orders.json", [])[0]))
    def test_amount_parsing(self):
        for value in (90000, 90000.0, "90000.00", "90000.0", "90.000đ"):
            self.assertEqual(server.parse_money(value), 90000)
        self.assertEqual(server.parse_money("-90000"), -90000)
    def test_bridge_requires_exact_memo_even_for_same_phone(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps({"data": {"data": [{"status": "PAID", "amount": 90000, "content": "PRO18T 0900000000 OLDMEMO"}]}}).encode()
        with patch.object(apipay_bridge, "load_config", return_value={"accessKey": "test", "secretKey": "test"}), patch.object(apipay_bridge.urllib.request, "urlopen", return_value=Response()):
            result = apipay_bridge.check_recent_payment_requests(self.order["memo"], self.order["phone"], 90000)
        self.assertFalse(result["paid"])
    def test_transaction_cannot_pay_second_order(self):
        tx = {"id": "BANK-1", "amount": 90000, "description": self.order["memo"]}
        self.assertIsNotNone(server.mark_order_paid("#TEST-A", "BANK-1", tx))
        orders = server.read_json_file("orders.json", [])
        orders.append(dict(self.order, orderId="#TEST-B"))
        server.write_json_file("orders.json", orders)
        self.assertIsNone(server.mark_order_paid("#TEST-B", "different-delivery-id", dict(tx, id="different-delivery-id")))
    def test_concurrent_completion_allocates_once(self):
        tx = {"id": "BANK-1", "amount": 90000, "description": self.order["memo"]}
        threads = [threading.Thread(target=server.mark_order_paid, args=("#TEST-A", "BANK-1", tx)) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(item["status"] == "Đã cấp" for item in server.read_licenses()), 1)
    def test_pending_failed_debit_and_underpaid_never_paid(self):
        for status in ["PENDING", "FAILED", "CANCELLED"]:
            self.post("/api/webhook", {"amount": 90000, "content": self.order["memo"], "status": status})
        self.post("/api/webhook", {"amount": 90000, "content": self.order["memo"], "transferType": "out"})
        self.post("/api/webhook", {"amount": 69000, "content": self.order["memo"], "status": "COMPLETED"})
        self.assertFalse(server.is_paid_order(server.read_json_file("orders.json", [])[0]))
    def test_client_cannot_suppress_server_sync_with_paidnotified(self):
        self.post("/api/orders", dict(self.order, paidNotified=True))
        self.assertNotIn("paidNotified", server.read_json_file("orders.json", [])[0])
    def test_sheet_failure_retried_and_tracking_forwarded(self):
        server.write_json_file("payment_config.json", {"googleSheetWebhookUrl": "https://example.invalid/webhook"})
        class Response:
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(self.payload).encode()
        calls=[]
        def fake_urlopen(req, **kwargs):
            if isinstance(req, str): return Response({"protocolVersion": 2})
            calls.append(json.loads(req.data))
            return Response({"status": "error"} if len(calls) == 1 else {"status": "success", "notificationsComplete": True})
        with patch.object(server.urllib.request, "urlopen", side_effect=fake_urlopen):
            server.sync_order_integrations("#TEST-A")
            self.assertNotIn("sheetSyncedHash", server.read_json_file("orders.json", [])[0])
            server.sync_order_integrations("#TEST-A")
            server.sync_order_integrations("#TEST-A")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1]["utmCampaign"], "Campaign")
        self.assertEqual(calls[-1]["ip"], "203.0.113.5")
        self.assertEqual(calls[-1]["action"], "pending_order")
    def test_old_script_rejected_without_posting(self):
        server.write_json_file("payment_config.json", {"googleSheetWebhookUrl": "https://example.invalid/webhook"})
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b'{"status":"success"}'
        with patch.object(server.urllib.request,"urlopen",return_value=Response()) as opener:
            server.sync_order_integrations("#TEST-A")
        self.assertEqual(opener.call_count, 1)
        self.assertIn("sheetSyncError", server.read_json_file("orders.json", [])[0])

if __name__ == "__main__": unittest.main()
