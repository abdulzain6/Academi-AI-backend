from google.cloud import firestore
from typing import List, Dict, Any
import os, json
def fetch_and_serialize_firestore_collection(collection_name: str) -> List[Dict[str, Any]]:
    # Initialize Firestore clie
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "akalmand-c6ec2-firebase-adminsdk-foxc7-2d8740a83e.json"
 
    db = firestore.Client()
    
    # Fetch all documents from the Firestore collection
    docs = db.collection(collection_name).stream()
    
    # Initialize an empty list to hold the serialized documents
    serialized_docs: List[Dict[str, Any]] = []
    
    # Loop through the documents and serialize each one
    for doc in docs:
        serialized_docs.append(doc.to_dict())
    
    return serialized_docs

if __name__ == "__main__":
    # Replace 'your_collection_name' with the name of your Firestore collection
    collection_name = "templates"
    
    # Fetch and serialize the Firestore collection
    serialized_docs = fetch_and_serialize_firestore_collection(collection_name)
    
    with open("templates.json", "w") as fp:
        json.dump(serialized_docs, fp)