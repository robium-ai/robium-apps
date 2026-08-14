import sys
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "scripts"))

from bundle_default_extension import rewrite_index  # noqa: E402


class BundleDefaultExtensionTest(unittest.TestCase):
    def test_replaces_the_main_bundle_with_an_awaited_extension_bootstrap(self):
        html = (
            '<html><head><script defer="defer" src="main.abc123.js"></script></head>'
            '<body><div id="root"></div></body></html>'
        )

        rewritten = rewrite_index(html, revision="abc123")

        self.assertNotIn('<script defer="defer" src="main.abc123.js"></script>', rewritten)
        self.assertIn(
            'import { installDefaultExtension } from "./robium/preinstall-extension.mjs?v=abc123";',
            rewritten,
        )
        self.assertIn("await installDefaultExtension({", rewritten)
        self.assertIn('baseUrl: "./robium/"', rewritten)
        self.assertIn('script.src = "main.abc123.js";', rewritten)
        self.assertIn("document.head.append(script);", rewritten)

    def test_rejects_an_upstream_page_without_exactly_one_main_bundle(self):
        with self.assertRaisesRegex(ValueError, "exactly one deferred main script"):
            rewrite_index("<html><head></head></html>")

        duplicate = (
            '<script defer="defer" src="main.one.js"></script>'
            '<script defer="defer" src="main.two.js"></script>'
        )
        with self.assertRaisesRegex(ValueError, "exactly one deferred main script"):
            rewrite_index(duplicate)


if __name__ == "__main__":
    unittest.main()
