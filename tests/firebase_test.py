import firebase_admin
from firebase_admin import credentials, auth
import requests


cred = credentials.Certificate("/home/zain/Akalmand.ai/api/creds/academi-ai-firebase-adminsdk-mg8gg-4dde2949d3.json")
firebase_admin.initialize_app(cred)

def login_with_email_and_password(email: str, password: str, api_key: str) -> str:
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        id_token = response.json().get("idToken")
        print("Login successful!")
        return id_token
    else:
        print("Login error:", response.json().get("error"))
        return None
    
def register_user(email, password):
    try:
        user = auth.create_user(
            email=email,
            password=password
        )
        print("User registered successfully!")
        return user
    except Exception as e:
        print("Registration error:", e)
        return None



email = "test@gmail.com"
password = "testpassword"

register_user(email, password)
register_user("zain1@gmail.com", password)

if id_token := login_with_email_and_password(email, password, "AIzaSyBdcuZHJyUFsGpKEG3-2TPl76Ax_Ehh-6c"):
    print("ID Token:", id_token)

if id_token := login_with_email_and_password("zain1@gmail.com", password, "AIzaSyBdcuZHJyUFsGpKEG3-2TPl76Ax_Ehh-6c"):
    print("\n\n\n\nID Token:", id_token)

