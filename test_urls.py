import urllib.request

urls = [
    'https://gach-ghar-team-jade.vercel.app/',
    'https://gach-ghar-team-jade.vercel.app/products/',
    'https://gach-ghar-team-jade.vercel.app/about/',
    'https://gach-ghar-team-jade.vercel.app/blog/',
    'https://gach-ghar-team-jade.vercel.app/guides/',
    'https://gach-ghar-team-jade.vercel.app/contact/',
]

with open('url_results.txt', 'w') as f:
    for u in urls:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            f.write(f'{u} -> {resp.status}\n')
        except urllib.error.HTTPError as e:
            f.write(f'{u} -> HTTP {e.code}: {e.reason}\n')
        except Exception as e:
            f.write(f'{u} -> ERROR: {e}\n')