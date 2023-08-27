import io
import logging
from fastapi.testclient import TestClient
from firebase import default_app
from api import app  
import requests
from firebase_admin import auth



email = 'abdulzain6@gmail.com'
password = 'zainzain' 
url = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSyDykoS37Pe-40VZSwE0eD4gSY-Dm-X3wr8'

data = {
    'email': email,
    'password': password,
    'returnSecureToken': True
}
response = requests.post(url, data=data)
id_token = response.json()['idToken']

client = TestClient(app)

def test_create_user():
    test_token = id_token
    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {test_token}"}
    )
    print(response.text)
    assert response.status_code == 200

def test_delete_user():
    test_token = id_token

    response = client.delete(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {test_token}"}
    )

    assert response.status_code == 200
    
def test_create_collection():
    # Replace with a valid Firebase ID token
    test_token = id_token
    collection_name = "test_collection"

    response = client.post(
        "/api/v1/collections",
        headers={"Authorization": f"Bearer {test_token}"},
        params={"name": collection_name, "description" : "desc"}
    )

    assert response.status_code == 200

def test_delete_collection():
    # Replace with a valid Firebase ID token
    test_token = id_token
    collection_name = "test_collection"

    response = client.delete(
        "/api/v1/collections",
        headers={"Authorization": f"Bearer {test_token}"},
        params={"name": collection_name}
    )

    assert response.status_code == 200

def test_update_collection():
    # Replace with a valid Firebase ID token
    test_token = id_token
    collection_name = "test_collection"
    collection_update = {"name": "new_collection_name"}

    response = client.put(
        f"/api/v1/collections/{collection_name}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=collection_update
    )

    assert response.status_code == 200
    assert response.json()["updated_rows"] > 0
    # Add more assertions based on what your endpoint should return

def test_get_user_collections():
    # Replace with a valid Firebase ID token
    test_token = id_token

    response = client.get(
        "/api/v1/users/collections",
        headers={"Authorization": f"Bearer {test_token}"}
    )
    logging.info(response.text)
    assert response.status_code == 200
    # Add more assertions based on what your endpoint should return

def test_create_file():
    # Replace with a valid Firebase ID token
    test_token = id_token
    collection_name = "new_collection_name"
    description = "test_description"

    # Create a test file
    test_file_content = b"test file content"
    test_file = io.BytesIO(test_file_content)
    test_file.name = "test_file.txt"

    # Create a multipart/form-data request with the file
    data = {
        "file": ("test_file.txt", test_file, "text/plain"),
    }
    response = client.post(
        f"/api/v1/users/collections/files?collection_name={collection_name}&description={description}",
        headers={"Authorization": f"Bearer {test_token}"},
        files=data
    )

    assert response.status_code == 200
    # Add more assertions based on what your endpoint should return

def test_get_files():
    # Replace with a valid Firebase ID token
    test_token = id_token
    collection_name = "new_collection_name"

    response = client.get(
        f"/api/v1/users/collections/files?collection_name={collection_name}",
        headers={"Authorization": f"Bearer {test_token}"}
    )
    logging.info(response.json())
    assert response.status_code == 200
    # Add more assertions based on what your endpoint should return

def test_delete_file():
    test_token = id_token
    response = client.delete(
        "/api/v1/users/collections/files",
        headers={"Authorization": f"Bearer {test_token}"},
        params={"collection_name": "new_collection_name", "file_name": "test_file.txt"}
    )
    assert response.status_code == 200
   # assert response.json() == {"status": "success", "error": "", "code" : 1}
