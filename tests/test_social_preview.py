from pathlib import Path
import struct
import unittest
from scripts.start_dashboard import add_metadata, IMAGE, TITLE

ROOT = Path(__file__).resolve().parents[1]

class SocialPreviewTests(unittest.TestCase):
    def test_shell_metadata_preserves_app_and_is_idempotent(self):
        original = '<html><head><title>Streamlit</title><script src="app.js"></script></head><body><div id="root"></div></body></html>'
        result = add_metadata(original)
        self.assertEqual(add_metadata(result), result)
        self.assertIn('<title>' + TITLE + '</title>', result)
        self.assertEqual(result.count('property="og:image"'), 1)
        self.assertIn(IMAGE, result)
        self.assertIn('<script src="app.js"></script>', result)
        self.assertIn('<div id="root"></div>', result)
        self.assertLess(result.index('property="og:title"'), result.index('</head>'))

    def test_unknown_shell_fails_explicitly(self):
        with self.assertRaises(RuntimeError):
            add_metadata('<html><body></body></html>')

    def test_public_png_matches_metadata_dimensions(self):
        data = (ROOT / 'static/diga-tracker-social-v1.png').read_bytes()
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', data[16:24]), (1200, 630))
        self.assertIn('enableStaticServing = true', (ROOT / '.streamlit/config.toml').read_text())
