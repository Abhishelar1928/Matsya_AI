import urllib.request, json, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def search_erddap(term):
    url = f'https://erddap.incois.gov.in/erddap/search/index.json?page=1&itemsPerPage=20&searchFor={term}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(res.read().decode())
        print(f'\n--- {term.upper()} ---')
        if 'table' in data and 'rows' in data['table']:
            for row in data['table']['rows'][:5]: # Print top 5 dataset IDs and titles
                dataset_id = row[data['table']['columnNames'].index('Dataset ID')]
                title = row[data['table']['columnNames'].index('Title')]
                print(f"ID: {dataset_id}")
                print(f"Title: {title}")
        else:
            print("No data found")
    except Exception as e:
        print(f'{term}: {e}')

if __name__ == '__main__':
    for t in ['sst', 'chlorophyll', 'wind', 'wave', 'current']:
        search_erddap(t)
