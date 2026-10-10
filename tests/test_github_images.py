import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_document_import import URL, ITEM, RAW
import document_import as documents
from prepare_github_image import prepare_image

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5WQAAAAASUVORK5CYII=')


class GithubImageTests(unittest.TestCase):
    def test_relative_image_included_without_forwarding_auth(self):
        metadata = {**documents.markdown_metadata(ITEM['name'], RAW), 'body': '# Doc\n![preview](assets/星.png)'}
        with patch('document_import.fetch_github', return_value=(URL, metadata, ITEM)), patch('document_import.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(PNG)
            source, result, files = documents.fetch_github_bundle(URL)
            self.assertEqual(source, URL)
            self.assertEqual(result['body'], metadata['body'])
            self.assertEqual(len(files), 2)
            self.assertEqual(base64.b64decode(files[1]['data']), PNG)
            request = opener.return_value.open.call_args.args[0]
            self.assertTrue(request.full_url.startswith('https://raw.githubusercontent.com/Yuji5124/idea-vault/main/ideas/assets/'))
            self.assertNotIn('Authorization', dict(request.header_items()))

    def test_external_traversal_svg_and_token_urls_not_downloaded(self):
        for relative in ('https://evil.example/x.png', '../private.png', '%2e%2e/private.png', '/image.png', 'image.svg', 'image.png?token=secret', 'image.png#secret'):
            with patch('document_import.fetch_github', return_value=(URL, {'body': f'![image]({relative})'}, ITEM)), patch('document_import.build_opener') as opener:
                with self.assertRaises(ValueError):
                    documents.fetch_github_bundle(URL)
                opener.assert_not_called()

    def test_oversized_bad_and_missing_images_fail_without_silent_omission(self):
        from urllib.error import HTTPError
        for raw in (b'<html>not an image</html>', PNG+b'x'*documents.MAX_IMAGE_BYTES):
            with patch('document_import.fetch_github', return_value=(URL, {'body': '![image](image.png)'}, ITEM)), patch('document_import.build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaises(ValueError):
                    documents.fetch_github_bundle(URL)
        with patch('document_import.fetch_github', return_value=(URL, {'body': '![image](image.png)'}, ITEM)), patch('document_import.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError(URL, 404, 'missing', {}, None)
            with self.assertRaises(ValueError):
                documents.fetch_github_bundle(URL)

    def test_more_than_four_images_refused(self):
        with patch('document_import.fetch_github', return_value=(URL, {'body': '\n'.join(f'![image](image{n}.png)' for n in range(5))}, ITEM)), patch('document_import.build_opener') as opener:
            with self.assertRaises(ValueError):
                documents.fetch_github_bundle(URL)
            opener.assert_not_called()

    def test_local_image_conversion_preserves_source_and_refuses_overwrite(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Optional local image preparation needs Pillow, not a Render dependency')
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory)/'original.png', Path(directory)/'archive.webp'
            Image.new('RGB', (2400, 1200), '#bcd123').save(source)
            original = source.read_bytes()
            result = prepare_image(source, destination)
            self.assertLessEqual(result['bytes'], documents.MAX_IMAGE_BYTES)
            self.assertEqual((result['width'], result['height']), (1600, 800))
            self.assertEqual(source.read_bytes(), original)
            with Image.open(destination) as image:
                self.assertEqual(image.format, 'WEBP')
                self.assertFalse(image.getexif())
            with self.assertRaises(ValueError):
                prepare_image(source, destination)
