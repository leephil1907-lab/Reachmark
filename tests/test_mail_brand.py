"""Branded e-mail: logo asset, HTML structure, base-URL fallbacks, multipart send."""
import json
import os
from unittest.mock import patch

import web.app as module
from tests.test_crew import CrewBase


def static_path(name):
    return os.path.join(os.path.dirname(module.__file__), '..', 'static', name)


class MailBrandTests(CrewBase):
    def test_logo_asset_exists_and_is_png(self):
        with open(static_path('logo-primary.png'), 'rb') as f:
            self.assertEqual(f.read(8), b'\x89PNG\r\n\x1a\n')

    def test_branded_html_has_logo_cta_and_footer(self):
        from web.accounts import branded_html
        with module.app.test_request_context('/'):
            html = branded_html('Hello Title', 'Line1\nLine2', cta_url='https://x.test/go',
                                cta_label='Go now', base_url='https://x.test')
        self.assertIn('https://x.test/static/logo-primary.png', html)
        self.assertIn('Go now', html)
        self.assertIn('https://x.test/go', html)
        self.assertIn('Hello Title', html)
        self.assertIn('Reachmark', html)

    def test_base_url_prefers_env_then_settings(self):
        from web.accounts import get_base_url
        with patch.dict(os.environ, {'PUBLIC_BASE_URL': 'https://env.test/'}):
            self.assertEqual(get_base_url(), 'https://env.test')
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('PUBLIC_BASE_URL', None)
            with module.db() as c:
                c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',
                          (json.dumps({'public_base_url': 'https://settings.test'}),))
            self.assertEqual(get_base_url(), 'https://settings.test')

    def test_send_branded_sends_multipart_with_html(self):
        from web.accounts import send_branded
        env = {'SMTP_HOST': 'smtp.test', 'SMTP_FROM': 'a@x.test', 'SMTP_PORT': '587',
               'SMTP_SECURITY': 'starttls', 'SMTP_USER': '',
               'PUBLIC_BASE_URL': 'https://x.test'}
        with patch.dict(os.environ, env):
            with patch('smtplib.SMTP') as smtp_cls:
                ok, _oid = send_branded('to@x.test', 'Sub', 'Text body', html_title='Title',
                                        cta_url='https://x.test/go', cta_label='Go', db=module.db)
        self.assertTrue(ok)
        sent = smtp_cls.return_value.__enter__.return_value.send_message.call_args[0][0]
        parts = {p.get_content_type(): p.get_content() for p in sent.walk() if not p.is_multipart()}
        self.assertIn('text/plain', parts)
        self.assertIn('text/html', parts)
        self.assertIn('/static/logo-primary.png', parts['text/html'])
