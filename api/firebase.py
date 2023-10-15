import os
import firebase_admin

current_directory = os.path.dirname(os.path.abspath(__file__))
credentials_path = os.path.join(current_directory, 'creds', 'academi-ai-firebase-adminsdk-mg8gg-4dde2949d3.json')

if not os.path.exists(credentials_path):
    raise FileNotFoundError(f"Credentials file not found at {credentials_path}")

cred = firebase_admin.credentials.Certificate(credentials_path)
default_app = firebase_admin.initialize_app(cred, {
    'storageBucket': "academi-ai.appspot.com"
})

