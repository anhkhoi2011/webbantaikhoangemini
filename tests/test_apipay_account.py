import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apipay_bridge

class ApiPayAccountTests(unittest.TestCase):
    def response(self, payload):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return response

    def config(self):
        return dict(accessKey='test', secretKey='test', bankPublicId='selected-bank', bankCode='BIDV', accountNo='V1T61023152838', accountName='NGO ANH KHOI', bankBin='970418')

    def test_connection_matches_configured_bank_instead_of_first(self):
        banks = [dict(publicId='other-bank', status='ACTIVE', accountName='Other'), dict(publicId='selected-bank', status='ACTIVE', accountName='NGO ANH KHOI', accountNumber='8809642706', bankShortName='BIDV')]
        with patch.object(apipay_bridge, 'load_config', return_value=self.config()), patch.object(apipay_bridge.urllib.request, 'urlopen', return_value=self.response({'data': {'message': banks}})):
            result = apipay_bridge.test_connection()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['accountNumber'], '8809642706')
        self.assertEqual(result['bankCode'], 'BIDV')

    def test_missing_or_inactive_selected_bank_is_error(self):
        for banks in [[], [dict(publicId='other-bank', status='ACTIVE')], [dict(publicId='selected-bank', status='INACTIVE')]]:
            with self.subTest(banks=banks), patch.object(apipay_bridge, 'load_config', return_value=self.config()), patch.object(apipay_bridge.urllib.request, 'urlopen', return_value=self.response({'data': {'message': banks}})):
                self.assertEqual(apipay_bridge.test_connection()['status'], 'error')

    def test_payment_request_uses_selected_bank_amount_and_exact_memo(self):
        with patch.object(apipay_bridge, 'load_config', return_value=self.config()), patch.object(apipay_bridge.urllib.request, 'urlopen', return_value=self.response({'data': {'publicId': 'TEST-QR'}})) as opener:
            result = apipay_bridge.create_payment_request('0900000000', 69000, 'PRO18T UNIQUE-ORDER')
        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload, {'bankPublicId': 'selected-bank', 'amount': 69000, 'content': 'PRO18T UNIQUE-ORDER'})
        self.assertEqual(result['bankCode'], 'BIDV')
        self.assertEqual(result['accountNumber'], 'V1T61023152838')

    def test_qr_uses_bidv_virtual_account_and_order_memo(self):
        with patch.object(apipay_bridge, 'load_config', return_value=self.config()), patch.object(apipay_bridge.urllib.request, 'urlopen', return_value=self.response({})) as opener:
            apipay_bridge.get_qr_base64('PRO18T UNIQUE-ORDER', 69000)
        url = opener.call_args.args[0].full_url
        self.assertIn('970418-V1T61023152838-compact2.png', url)
        self.assertIn('amount=69000', url)
        self.assertIn('addInfo=PRO18T%20UNIQUE-ORDER', url)

    def test_recent_requests_skip_old_payments_for_reused_phone_reference(self):
        from datetime import datetime, timedelta, timezone
        created = datetime.now(timezone.utc) - timedelta(minutes=5)
        old = dict(publicId='OLD', status='PAID', amount=90000, content='PRO18T 0900000000', createdAt=(created - timedelta(hours=1)).isoformat())
        fresh = dict(old, publicId='NEW', createdAt=(created + timedelta(minutes=1)).isoformat())
        for rows, expected in [([old], False), ([old, fresh], True)]:
            with self.subTest(expected=expected), patch.object(apipay_bridge, 'load_config', return_value=self.config()), patch.object(apipay_bridge.urllib.request, 'urlopen', return_value=self.response({'data': {'data': rows}})):
                result = apipay_bridge.check_recent_payment_requests('PRO18T 0900000000', '0900000000', 90000, not_before=created.isoformat())
            self.assertEqual(result['paid'], expected)
            if expected:
                self.assertEqual(result['transaction']['publicId'], 'NEW')

if __name__ == '__main__':
    unittest.main()
