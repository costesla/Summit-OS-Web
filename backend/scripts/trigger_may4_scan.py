import urllib.request, json, time

url = 'https://summitos-api.azurewebsites.net/api/operations/trigger-cloud-scan'
path = 'Uber Driver/2026/May/Week 1/04'
payload = json.dumps({'path': path}).encode('utf-8')
req = urllib.request.Request(url, method='POST', data=payload, headers={'Content-Type': 'application/json'})

print('Triggering cloud scan for:', path)
print('Started at:', time.strftime('%H:%M:%S'))

try:
    r = urllib.request.urlopen(req, timeout=300)
    body = r.read().decode()
    data = json.loads(body)
    print('Status:', r.getcode())
    print('Success:', data.get('success'))
    print('Processed:', data.get('processed'))
    print('Matched:', data.get('matched'))
    print('Logs:')
    for log in data.get('logs', []):
        print(' ', log)
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code)
    print('Body:', e.read().decode()[:500])
except Exception as e:
    print('Error/timeout:', e)

print('Done at:', time.strftime('%H:%M:%S'))
