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
print(response.text)

