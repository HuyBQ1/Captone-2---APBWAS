"""Wait for the local health endpoint without requiring curl/requests in CI."""
import sys,time,urllib.request,urllib.error

url=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:4181/api/health/ready'
deadline=time.monotonic()+90
while time.monotonic()<deadline:
    try:
        with urllib.request.urlopen(url,timeout=3) as response:
            if response.status==200:
                print('Application is ready.');break
    except (urllib.error.URLError,TimeoutError):pass
    time.sleep(1)
else:raise SystemExit('Application did not become ready within 90 seconds.')
