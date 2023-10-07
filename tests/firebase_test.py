import firebase_admin
from firebase_admin import credentials, auth
import requests


cred = credentials.Certificate("akalmand-c6ec2-firebase-adminsdk-foxc7-2d8740a83e.json")
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



email = "test@example.com"
password = "testpassword"

register_user(email, password)
register_user("zain@example.com", password)

if id_token := login_with_email_and_password(email, password, "AIzaSyDykoS37Pe-40VZSwE0eD4gSY-Dm-X3wr8"):
    print("ID Token:", id_token)

if id_token := login_with_email_and_password("zain@example.com", password, "AIzaSyDykoS37Pe-40VZSwE0eD4gSY-Dm-X3wr8"):
    print("\n\n\n\nID Token:", id_token)

print("\n" + "683DA5D3-D11D-43DD-9FC7-0E4FEFEAD131")