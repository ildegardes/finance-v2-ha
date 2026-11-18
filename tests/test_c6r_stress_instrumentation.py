"""Synthetic negative check for the C6R diagnostic tracer."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest

from c6r_stress_campaign import exception_tracer
from test_gate_c6r import DatabaseCase
from finance_v2.open_finance_coverage import sync_domain


class StressInstrumentationTests(DatabaseCase):
    def test_caught_exception_records_type_and_stage_without_message(self):
        caught = []
        def reject_client(_config):
            raise ValueError('synthetic confidential payload must not appear')
        self.service.client_factory = reject_client
        threading.settrace(exception_tracer(caught, threading.Lock()))
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(sync_domain, self.service, 'itau', actor='UI:local').result(10)
        finally:
            threading.settrace(None)
        self.assertEqual(result['error_code'], 'COVERAGE_INVALID_OR_STORAGE_FAILURE')
        self.assertTrue(any(item['type'] == 'ValueError' for item in caught))
        self.assertTrue(any('_sync_full' in str(item['stack']) for item in caught))
        self.assertNotIn('confidential', json.dumps(caught))


if __name__ == '__main__':
    unittest.main()
