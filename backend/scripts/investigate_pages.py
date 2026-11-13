import urllib.request, ssl, re, json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls_to_test = [
    'https://incois.gov.in/portal/osf/osf.jsp',
    'https://incois.gov.in/portal/pfz.jsp',
]

for url in urls_to_test:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, context=ctx, timeout=10)
        html = res.read().decode('utf-8', errors='ignore')
        
        print(f'--- {url} ---')
        print('Length:', len(html))
        
        api_urls = re.findall(r'(https?://[^\'\"<>]+)', html)
        for u in set(api_urls):
            if 'api' in u.lower() or 'data' in u.lower() or 'json' in u.lower() or 'xml' in u.lower() or 'csv' in u.lower() or 'wfs' in u.lower() or 'thredds' in u.lower():
                print('-', u)
    except Exception as e:
        print(f'Error fetching {url}: {e}')
