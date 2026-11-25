import json
from store.models import Guide, BlogPost
from pathlib import Path

fixture_dir = Path('store/fixtures')

print('Loading guides...')
guide_fixture = fixture_dir / 'guide_content.json'
guides = json.loads(guide_fixture.read_text(encoding='utf-8'))
print(f'Found {len(guides)} guides in fixture')
for g in guides:
    obj, created = Guide.objects.get_or_create(slug=g['slug'], defaults=g)
    print(f'  {obj.title}: created={created}')

print('Loading blog posts...')
blog_fixture = fixture_dir / 'blog_content.json'
posts = json.loads(blog_fixture.read_text(encoding='utf-8'))
print(f'Found {len(posts)} blog posts in fixture')
for p in posts:
    obj, created = BlogPost.objects.get_or_create(slug=p['slug'], defaults=p)
    print(f'  {obj.title}: created={created}')

print('Done!')
print(f'Total guides: {Guide.objects.count()}, published: {Guide.objects.filter(is_published=True).count()}')
print(f'Total blog posts: {BlogPost.objects.count()}, published: {BlogPost.objects.filter(is_published=True).count()}')