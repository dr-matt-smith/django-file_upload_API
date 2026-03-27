import requests
from config import BASE_URL, USERNAME, PASSWORD

session = requests.Session()

# Get CSRF token
login_page = session.get(f"{BASE_URL}/admin/login/")
csrf_token = session.cookies.get("csrftoken")

# Log in
response = session.post(f"{BASE_URL}/admin/login/", data={
    "username": USERNAME,
    "password": PASSWORD,
    "csrfmiddlewaretoken": csrf_token,
    "next": "/admin/",
})

if "Log in" in response.text:
    print("Login failed. Check your credentials.")
    exit(1)

print("Logged in successfully.")

# Get file list
response = session.get(f"{BASE_URL}/api/files/")

if response.status_code == 200:
    files = response.json()
    print(f"Found {len(files)} file(s):")
    for f in files:
        print(f"  [{f['id']}] {f['file']} — {f['file_size']} bytes — {f['uploaded_at']}")
else:
    print(f"Request failed ({response.status_code}):")
    print(response.text)