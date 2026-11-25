import urllib.request
import urllib.error

urls = [
    'https://gach-ghar-team-jade.vercel.app/',
    'https://gach-ghar-team-jade.vercel.app/products/',
    'https://gach-ghar-team-jade.vercel.app/about/',
    'https://gach-ghar-team-jade.vercel.app/blog/',
    'https://gach-ghar-team-jade.vercel.app/guides/',
    'https://gach-ghar-team-jade.vercel.app/contact/',
]

for u in urls:
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        print(f'{u} -> {resp.status}')
    except urllib.error.HTTPError as e:
        print(f'{u} -> HTTP {e.code}: {e.reason}')
    except Exception as e:
        print(f'{u} -> ERROR: {e}')