import urllib.request, ssl, xml.etree.ElementTree as ET

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_url(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, context=ctx, timeout=5)
        return True, res.read()
    except Exception as e:
        return False, str(e)

print("--- PFZ ---")
ok, data = test_url('https://incois.gov.in/portal/pfz.jsp')
if ok:
    html = data.decode('utf-8', errors='ignore').lower()
    print("Found 'wms':", 'wms' in html)
    print("Found 'wfs':", 'wfs' in html)
    print("Found 'geojson':", 'geojson' in html)
else:
    print("PFZ failed:", data)

print("\n--- THREDDS ---")
ok, data = test_url('https://las.incois.gov.in/thredds/catalog.xml')
if ok:
    try:
        tree = ET.fromstring(data)
        ns = {'thredds': 'http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'}
        print("Datasets:")
        for ds in tree.findall('.//thredds:dataset', ns)[:5]:
            print(ds.get('name'))
        refs = tree.findall('.//thredds:catalogRef', ns)
        print("CatalogRefs:")
        for ref in refs[:5]:
            print(ref.get('xlink:title'), ref.get('xlink:href'))
    except Exception as e:
        print("XML Parse error:", e)
else:
    print("THREDDS failed:", data)

print("\n--- IMD ---")
ok, data = test_url('https://mausam.imd.gov.in/api/marine_forecast')
print("Marine forecast API:", "OK" if ok else data)

ok, data = test_url('https://api.imd.gov.in/')
if ok:
    html = data.decode('utf-8', errors='ignore').lower()
    print("api.imd.gov.in accessible:", True)
    print("Mentions 'register':", 'register' in html)
    print("Mentions 'login':", 'login' in html)
else:
    print("api.imd.gov.in failed:", data)

