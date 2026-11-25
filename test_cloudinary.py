#!/usr/bin/env python
"""Test Cloudinary configuration and upload."""
import os
import sys

# Set environment variables BEFORE importing Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['CLOUDINARY_CLOUD_NAME'] = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
os.environ['CLOUDINARY_API_KEY'] = os.environ.get('CLOUDINARY_API_KEY', '')
os.environ['CLOUDINARY_API_SECRET'] = os.environ.get('CLOUDINARY_API_SECRET', '')
os.environ['DJANGO_DEBUG'] = 'False'

import django
django.setup()

from django.conf import settings
from django.core.files.base import ContentFile
from store.storage import CloudinaryMediaStorage

print("=== Cloudinary Configuration Test ===")
print(f"DEBUG: {settings.DEBUG}")
print(f"CLOUDINARY_CLOUD_NAME: {settings.CLOUDINARY_CLOUD_NAME}")
print(f"CLOUDINARY_API_KEY: {settings.CLOUDINARY_API_KEY[:10] if settings.CLOUDINARY_API_KEY else 'NOT SET'}")
print(f"CLOUDINARY_API_SECRET: {'SET' if settings.CLOUDINARY_API_SECRET else 'NOT SET'}")
print(f"CLOUDINARY_CONFIGURED: {settings.CLOUDINARY_CONFIGURED}")
print(f"STORAGES default: {settings.STORAGES.get('default')}")

if not settings.CLOUDINARY_CONFIGURED:
    print("\n❌ Cloudinary not configured - missing environment variables")
    print("Required: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET")
    sys.exit(1)

# Test storage
storage = CloudinaryMediaStorage()
print(f"\nStorage backend: {storage.__class__.__name__}")

# Test upload with a small test image
print("\n=== Testing Upload ===")
try:
    # Create a minimal test image (1x1 pixel PNG)
    test_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x00\x00\x00\x00IEND\xaeB`\x82'
    content = ContentFile(test_image_data, name='test.png')
    
    saved_name = storage._save('test/test.png', content)
    print(f"✅ Upload successful! Saved as: {saved_name}")
    
    # Test URL generation
    url = storage.url(saved_name)
    print(f"✅ URL generation successful: {url}")
    
    # Test delete
    storage.delete(saved_name)
    print(f"✅ Delete successful!")
    
except Exception as e:
    print(f"❌ Upload failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== All tests passed! ===")