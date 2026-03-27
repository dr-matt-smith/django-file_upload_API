import requests
from config import BASE_URL, USERNAME, PASSWORD

FILE_PATH = "Week12.zip"

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

# Upload file
with open(FILE_PATH, "rb") as f:
    response = session.post(
        f"{BASE_URL}/api/upload/",
        files={"file": (FILE_PATH, f, "application/zip")},
        headers={"X-CSRFToken": session.cookies.get("csrftoken")},
    )

if response.status_code == 201:
    print("File uploaded successfully.")
    print(response.json())
else:
    print(f"Upload failed ({response.status_code}):")
    print(response.text)