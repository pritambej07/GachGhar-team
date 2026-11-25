#!/usr/bin/env python
"""Test Cloudinary upload with environment variables set in the script."""
import os

# Set environment variables HERE - these will persist for the script
os.environ['CLOUDINARY_CLOUD_NAME'] = os.environ.get('CLOUDINARY_CLOUD_NAME', 'qrinm3mf')
os.environ['CLOUDINARY_API_KEY'] = os.environ.get('CLOUDINARY_API_KEY', '839243423872917')
os.environ['CLOUDINARY_API_SECRET'] = os.environ.get('CLOUDINARY_API_SECRET', 'oKSm1l7zvoZuc1q2b_zTeTLho_g')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DJANGO_DEBUG'] = 'True'
os.environ['DATABASE_URL'] = 'sqlite:///db.sqlite3'

import django
django.setup()

import cloudinary.uploader
from django.core.files.base import ContentFile

print("=== Testing Cloudinary Direct Upload ===")
test_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x00\x00\x00\x00IEND\xaeB`\x82'
content = ContentFile(test_data, name='test.png')

try:
    result = cloudinary.uploader.upload(
        content,
        public_id='test/test',
        resource_type='image',
        overwrite=False,
        unique_filename=False
    )
    print('✅ Upload successful!')
    print(f'Public ID: {result["public_id"]}')
    print(f'URL: {result["secure_url"]}')
    print(f'Format: {result["format"]}')
    print(f'Width: {result["width"]}, Height: {result["height"]}')
    
    # Test URL generation
    from cloudinary.utils import cloudinary_url
    url, _ = cloudinary_url('test/test', format='png', resource_type='image', secure=True)
    print(f'Generated URL: {url}')
    
    # Clean up
    cloudinary.uploader.destroy('test/test', resource_type='image', invalidate=True)
    print('✅ Cleanup successful!')
    
except Exception as e:
    print(f'❌ Upload failed: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    exit(1)

print("\n=== Testing Django Storage ===")
from store.storage import CloudinaryMediaStorage
from django.core.files.base import ContentFile

storage = CloudinaryMediaStorage()
test_data2 = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x00\x00\x00\x00IEND\xaeB`\x82'
content2 = ContentFile(test_data2, name='test2.png')

try:
    saved = storage._save('test/test2.png', content2)
    print(f'✅ Django storage save: {saved}')
    url = storage.url(saved)
    print(f'URL: {url}')
    storage.delete(saved)
    print('✅ Django storage delete OK!')
except Exception as e:
    print(f'❌ Django storage failed: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    exit(1)

print("\n=== All tests passed! ===")