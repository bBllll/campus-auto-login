import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import campus_auto_login as app
from portal_config import load_portal, save_portal, validate_portal


class PortalConfigurationTests(unittest.TestCase):
    def test_no_gateway_is_published_as_default(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(load_portal(root), '')

    def test_gateway_roundtrip_and_redirect_query(self):
        url = 'https://portal.example.invalid/?url=http://example.com/'
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(save_portal(root, url), url)
            self.assertEqual(load_portal(root), url)

    def test_invalid_config_does_not_break_import(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'portal.json').write_text('not json', encoding='utf-8')
            self.assertEqual(load_portal(root), '')
            (Path(root) / 'portal.json').write_text(json.dumps({'url': 'file:///private'}), encoding='utf-8')
            self.assertEqual(load_portal(root), '')

    def test_rejects_missing_host_non_web_schemes_credentials_and_unexpected_ports(self):
        for url in ('', 'file:///private', 'javascript:alert(1)', 'https://', 'http://user:secret@portal.example.invalid/',
                    'http://portal.example.invalid:1234/', 'https://portal.example.invalid:notaport/', 'http://bad host/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_portal(url)

    def test_unconfigured_login_does_not_open_browser_or_submit(self):
        with patch.object(app, 'HOST', ''), patch.object(app, 'Browser') as browser:
            with self.assertRaisesRegex(RuntimeError, '尚未配置'):
                app.run_login({}, lambda message: None, internet_check=lambda: False)
            browser.assert_not_called()

    def test_https_gateway_probe_uses_secure_port(self):
        with patch.object(app, 'HOST', 'portal.example.invalid'), patch.object(app, 'PORTAL', 'https://portal.example.invalid/'), patch.object(app.socket, 'create_connection') as connect:
            self.assertTrue(app.portal_reachable())
            connect.assert_called_once_with(('portal.example.invalid', 443), timeout=3)

    def test_dom_host_matches_current_configuration(self):
        with patch.object(app, 'HOST', 'configured.example.invalid'):
            self.assertIn('configured.example.invalid', app.dom_script('inspect'))

    def test_status_probe_is_skipped_without_configuration(self):
        with patch.object(app, 'HOST', ''), patch.object(app.OPENER, 'open') as opener:
            self.assertFalse(app.campus_online())
            opener.assert_not_called()

    def test_cli_saves_only_to_selected_user_folder(self):
        with tempfile.TemporaryDirectory() as root:
            entry = Path(__file__).resolve().parents[1] / 'campus_auto_login.py'
            result = subprocess.run([sys.executable, '-X', 'utf8', str(entry), '--set-portal', 'https://portal.example.invalid/'],
                                    env=dict(os.environ, LOCALAPPDATA=root), capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(load_portal(Path(root) / 'CampusAutoLogin'), 'https://portal.example.invalid/')


if __name__ == '__main__':
    unittest.main()
