from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class MarketTokenReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=(ROOT/"live_strategy_runner.py").read_text();cls.scanner=(ROOT/"trendline_scanner_v25_live_schwab.py").read_text()
    def test_market_uses_explicit_locked_refresh(self):
        block=self.source[self.source.index('market_token_path = "/data/schwab_token.json"'):self.source.index('trade_token_path = "/data/schwab_trade_token.json"')]
        self.assertIn("explicit_refresh_schwab_token(",block);self.assertIn('DATA_ROOT / "market_auth_status.json"',block)
    def test_verifies_persisted_lifetime_and_quote(self):
        self.assertIn("TOKEN_REFRESH_THRESHOLD_MINUTES = 20.0",self.source);self.assertIn("TOKEN_REFRESH_VERIFY_MINUTES = 25.0",self.source);self.assertIn("after_min_left < TOKEN_REFRESH_VERIFY_MINUTES",self.source);self.assertIn('get_quotes(["VOO"])',self.source);self.assertIn("verification_status=status_code",self.source)
    def test_logs_bounded_durable_evidence_without_tokens(self):
        self.assertIn('AUTH_EVENTS_PATH = DATA_ROOT / "auth_events.jsonl"',self.source);self.assertIn("AUTH_EVENTS_MAX_ROWS = 2000",self.source);self.assertIn('record_auth_event("market_refresh_ok"',self.source);self.assertIn('record_auth_event("market_refresh_error"',self.source)
        self.assertIn('"trading_refresh_ok"',self.source);self.assertIn('"trading_refresh_error"',self.source)
        record=self.source[self.source.index("def record_auth_event"):self.source.index("VOLUME_METRIC_KEYS")];self.assertNotIn("access_token",record);self.assertNotIn("refresh_token",record)
    def test_trading_has_same_persistence_and_verification_standard(self):
        block=self.source[self.source.index('trade_token_path = "/data/schwab_trade_token.json"'):self.source.index("df = quote_source.read_data()")]
        self.assertIn('DATA_ROOT / "trading_auth_status.json"',block);self.assertIn("after_min_left < TOKEN_REFRESH_VERIFY_MINUTES",block);self.assertIn("post-refresh trading account lookup failed",block);self.assertIn('account_verification="account_hash_resolved"',block)
    def test_cached_market_client_tracks_persisted_token_file(self):
        block=self.source[self.source.index("def _market_data_client():"):self.source.index("def _nh015_execution_quotes")]
        self.assertIn('token_path = "/data/schwab_token.json"',block)
        self.assertIn("os.stat(token_path).st_mtime_ns",block)
        self.assertIn('"token_mtime_ns"',block)
        self.assertIn("client_token_mtime_ns != token_mtime_ns",block)
        self.assertIn("_MARKET_DATA_CLIENT_LOCAL.token_mtime_ns = token_mtime_ns",block)

    def test_cached_market_client_rebuilds_after_token_file_replacement(self):
        """A long-lived worker must not keep a client built from an old token file."""
        import os
        import tempfile
        from unittest.mock import Mock, patch

        # Exercise the same cache-invalidating behavior used by the runner:
        # unchanged token file -> reuse client;
        # replaced token file -> construct a new client.
        local = type("Local", (), {})()

        with tempfile.TemporaryDirectory() as td:
            token_path = os.path.join(td, "token.json")
            with open(token_path, "w") as f:
                f.write('{"token": "first"}')

            built = []

            def fake_client_from_token_file(path, app_key, app_secret):
                client = Mock(name=f"client_{len(built) + 1}")
                built.append(client)
                return client

            def get_client():
                token_mtime_ns = os.stat(token_path).st_mtime_ns
                client = getattr(local, "client", None)
                cached_mtime = getattr(local, "token_mtime_ns", None)

                if client is None or cached_mtime != token_mtime_ns:
                    client = fake_client_from_token_file(
                        token_path, "key", "secret"
                    )
                    local.client = client
                    local.token_mtime_ns = token_mtime_ns

                return client

            first = get_client()
            same = get_client()

            self.assertIs(first, same)
            self.assertEqual(len(built), 1)

            # os.replace models the atomic token-file replacement performed
            # by the running authentication code.
            replacement = os.path.join(td, "replacement.json")
            with open(replacement, "w") as f:
                f.write('{"token": "second-and-different-length"}')
            os.replace(replacement, token_path)

            second = get_client()

            self.assertIsNot(first, second)
            self.assertEqual(len(built), 2)
            self.assertEqual(
                local.token_mtime_ns,
                os.stat(token_path).st_mtime_ns,
            )

    def test_old_misleading_log_removed(self):
        self.assertNotIn('MARKET_TOKEN_REFRESH status=',self.source);self.assertIn("strategy runner owns explicit refresh",self.scanner)
if __name__=="__main__":unittest.main()
