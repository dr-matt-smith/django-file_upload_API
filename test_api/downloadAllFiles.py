import requests
import os
from datetime import datetime
from config import BASE_URL, USERNAME, PASSWORD
DOWNLOAD_DIR = os.path.join("downloads", datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))

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

if response.status_code != 200:
    print(f"Failed to retrieve file list ({response.status_code}):")
    print(response.text)
    exit(1)

files = response.json()
print(f"Found {len(files)} file(s).")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Download each file
for f in files:
    file_id = f["id"]
    filename = os.path.basename(f["file"])
    dest = os.path.join(DOWNLOAD_DIR, filename)

    response = session.get(f"{BASE_URL}/api/files/{file_id}/")

    if response.status_code == 200:
        with open(dest, "wb") as out:
            out.write(response.content)
        print(f"Downloaded: {filename} -> {dest}")
    else:
        print(f"Failed to download file {file_id} ({response.status_code})")