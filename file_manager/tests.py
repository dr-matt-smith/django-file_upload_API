from django.test import TestCase
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.conf import settings
from .models import UploadedFile
import io
import os
import zipfile

def make_zip(files: dict) -> bytes:
    """Helper: create an in-memory ZIP. files = {filename: bytes_content}"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class FileUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
    def test_upload_file(self):
        file_content = b'Test content'
        test_file = SimpleUploadedFile('test.txt', file_content)
        response = self.client.post('/api/upload/', {'file': test_file}, format='multipart')
        
        self.assertEqual(response.status_code, 201)
        self.assertEqual(UploadedFile.objects.count(), 1)
        self.assertEqual(UploadedFile.objects.first().file_size, len(file_content))
        
    def test_list_files(self):
        file_content = b'Test content'
        test_file = SimpleUploadedFile('test.txt', file_content)
        UploadedFile.objects.create(file=test_file)
        
        response = self.client.get('/api/files/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        
    def test_retrieve_file(self):
        file_content = b'Test content'
        test_file = SimpleUploadedFile('test.txt', file_content)
        uploaded_file = UploadedFile.objects.create(file=test_file)
        
        response = self.client.get(f'/api/files/{uploaded_file.id}/')
        self.assertEqual(response.status_code, 200)
        # Read streaming content for FileResponse
        content = b''.join(response.streaming_content)
        self.assertEqual(content, file_content)
        
    def test_delete_file(self):
        file_content = b'Test content'
        test_file = SimpleUploadedFile('test.txt', file_content)
        uploaded_file = UploadedFile.objects.create(file=test_file)

        response = self.client.delete(f'/api/files/{uploaded_file.id}/delete/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(UploadedFile.objects.count(), 0)


class ZipUnzipTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='zipuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _upload_zip(self, filename, files):
        zip_bytes = make_zip(files)
        uploaded = SimpleUploadedFile(filename, zip_bytes, content_type='application/zip')
        return self.client.post('/api/upload/', {'file': uploaded}, format='multipart')

    def test_zip_upload_creates_public_folder(self):
        response = self._upload_zip('matt.zip', {'hello.txt': b'hello world'})
        self.assertEqual(response.status_code, 201)
        self.assertIn('public_url', response.data)
        self.assertEqual(response.data['public_url'], '/public/matt/')
        dest = os.path.join(settings.PUBLIC_ROOT, 'matt')
        self.assertTrue(os.path.isdir(dest))
        self.assertTrue(os.path.exists(os.path.join(dest, 'hello.txt')))

    def test_zip_without_index_generates_one(self):
        self._upload_zip('monday12.zip', {'data.csv': b'a,b,c'})
        index_path = os.path.join(settings.PUBLIC_ROOT, 'monday12', 'index.html')
        self.assertTrue(os.path.exists(index_path))
        with open(index_path) as f:
            content = f.read()
        self.assertIn('data.csv', content)
        self.assertIn('<a href=', content)

    def test_zip_with_index_preserves_it(self):
        custom_index = b'<html><body>my custom page</body></html>'
        self._upload_zip('site.zip', {'index.html': custom_index, 'style.css': b'body{}'})
        index_path = os.path.join(settings.PUBLIC_ROOT, 'site', 'index.html')
        with open(index_path, 'rb') as f:
            self.assertEqual(f.read(), custom_index)

    def test_reupload_replaces_existing_folder(self):
        self._upload_zip('proj.zip', {'old.txt': b'old content'})
        self._upload_zip('proj.zip', {'new.txt': b'new content'})
        dest = os.path.join(settings.PUBLIC_ROOT, 'proj')
        self.assertFalse(os.path.exists(os.path.join(dest, 'old.txt')))
        self.assertTrue(os.path.exists(os.path.join(dest, 'new.txt')))

    def test_path_traversal_in_zip_is_skipped(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('../evil.txt', b'should not escape')
            zf.writestr('safe.txt', b'safe content')
        zip_bytes = buf.getvalue()
        uploaded = SimpleUploadedFile('hack.zip', zip_bytes, content_type='application/zip')
        self.client.post('/api/upload/', {'file': uploaded}, format='multipart')
        # evil.txt must not have been written outside the dest directory
        escaped_path = os.path.join(settings.PUBLIC_ROOT, 'evil.txt')
        self.assertFalse(os.path.exists(escaped_path))
        # safe file should be present
        self.assertTrue(os.path.exists(os.path.join(settings.PUBLIC_ROOT, 'hack', 'safe.txt')))

    def test_non_zip_upload_has_no_public_url(self):
        txt = SimpleUploadedFile('readme.txt', b'just text')
        response = self.client.post('/api/upload/', {'file': txt}, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('public_url', response.data)