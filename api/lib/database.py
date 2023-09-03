import uuid
import base64
from firebase_admin import firestore, storage
from firebase_admin.firestore import DocumentSnapshot
from typing import Dict, List, Optional
from .models import UserModel, CollectionModel, FileModel


class UserDBManager:
    def __init__(self) -> None:
        self.db = firestore.client()
        self.user_collection = self.db.collection('users')
        self.collection_manager = CollectionDBManager()

    def get_all_vector_ids_for_user(self, user_id: str) -> Dict[str, List[str]]:
        vector_ids_per_collection = {}
        user_collections = self.collection_manager.get_all_by_user(user_id)
        for collection in user_collections:
            collection_name = collection.name
            vectordb_collection_name = collection.vectordb_collection_name
            collection_vector_ids = self.collection_manager.get_all_vector_ids(user_id, collection_name)
            vector_ids_per_collection[vectordb_collection_name] = collection_vector_ids
        return vector_ids_per_collection
    
    def add_user(self, user_model: UserModel) -> UserModel:
        doc_ref = self.user_collection.document(user_model.uid)
        if doc_ref.get().exists:
            raise ValueError("User already exists")
        
        user_data = user_model.model_dump()
        doc_ref.set(user_data)
        return user_model

    def get_user_by_uid(self, uid: str) -> Optional[UserModel]:
        doc_ref = self.user_collection.document(uid)
        doc: DocumentSnapshot = doc_ref.get()
        return UserModel(**doc.to_dict()) if doc.exists else None
    
    def user_exists(self, uid: str):
        doc_ref = self.user_collection.document(uid)
        doc: DocumentSnapshot = doc_ref.get() 
        return doc.exists

    def get_all(self) -> List[UserModel]:
        return [UserModel(**doc.to_dict()) for doc in self.user_collection.stream()]

    def insert_many(self, rows: List[UserModel]) -> None:
        batch = self.db.batch()
        for user_model in rows:
            doc_ref = self.user_collection.document(user_model.uid)
            batch.set(doc_ref, user_model.model_dump())
        batch.commit()

    def update_user(self, uid: str, **kwargs: dict) -> int:
        doc_ref = self.user_collection.document(uid)
        doc_ref.update(kwargs)
        return 1

    def delete_user(self, uid: str) -> int:
        if not self.user_exists(uid):
            return 0
            
        self.collection_manager.delete_all(uid)
        doc_ref = self.user_collection.document(uid)
        doc_ref.delete()

        return 1

class CollectionDBManager:
    def __init__(self) -> None:
        self.db = firestore.client()
        self.user_collection = self.db.collection('users')
        self.bucket = storage.bucket() # Initialize Cloud Storage bucket
        
    def collection_exists(self, name: str, user_id: str) -> bool:
        user_ref = self.user_collection.document(user_id)
        collections_query = user_ref.collection('collections').where("name", "==", name).stream()
        return any(collections_query)
    
    def get_all_vector_ids(self, user_id: str, collection_name: str) -> List[str]:
        all_vector_ids = []
        user_ref = self.user_collection.document(user_id)
        collections_query = user_ref.collection('collections').where("name", "==", collection_name).stream()

        for collection_doc in collections_query:
            collection_ref = collection_doc.reference
            files_query = collection_ref.collection('files').stream()

            for file_doc in files_query:
                file_data = file_doc.to_dict()
                vector_ids = file_data.get('vector_ids', [])
                all_vector_ids.extend(vector_ids)

        return all_vector_ids

    def add_collection(self, collection_model: CollectionModel) -> CollectionModel:
        user_ref = self.user_collection.document(collection_model.user_uid)
        if not user_ref.get().exists:
            raise ValueError("User not found")

        collection_data = collection_model.model_dump()
        user_ref.collection('collections').add(collection_data) # Auto-generate ID
        return collection_model

    def get_collection_by_name_and_user(self, name: str, user_id: str) -> Optional[CollectionModel]:
        user_ref = self.user_collection.document(user_id)
        collections_query = user_ref.collection('collections').where("name", "==", name).stream()
        for doc in collections_query:
            collection_data = doc.to_dict()
            # Retrieve the reference to the collection
            collection_ref = doc.reference
            
            # Count the number of files in the collection
            number_of_files = len(list(collection_ref.collection('files').stream()))
            
            # Add the number_of_files to the collection data
            collection_data['number_of_files'] = number_of_files
            
            return CollectionModel(**collection_data)
        return None
    
    def get_all_by_user(self, user_id: str) -> List[CollectionModel]:
        user_ref = self.user_collection.document(user_id)
        collections = []
        for doc in user_ref.collection('collections').stream():
            collection_data = doc.to_dict()
            
            # Retrieve the reference to the collection
            collection_ref = doc.reference
            
            # Count the number of files in the collection
            number_of_files = len(list(collection_ref.collection('files').stream()))
            
            # Add the number_of_files to the collection data
            collection_data['number_of_files'] = number_of_files
            
            collections.append(CollectionModel(**collection_data))
        
        return collections

    def update_collection(self, user_id: str, collection_id: str, **kwargs: dict) -> int:
        user_ref = self.user_collection.document(user_id)
        collection_ref = user_ref.collection('collections').document(collection_id)

        if collection_ref.get().exists:
            # Update the fields with the kwargs
            collection_ref.update(kwargs)
            return 1

        return 0

    def delete_collection(self, user_id: str, collection_name: str) -> int:
        user_ref = self.user_collection.document(user_id)
        collections_query = user_ref.collection('collections').where("name", "==", collection_name).stream()
        for collection_doc in collections_query:
            collection_ref = collection_doc.reference

            # Get all file references in the collection
            file_refs = collection_ref.collection('files').stream()

            # Delete each file from Cloud Storage
            for file_doc in file_refs:
                file_uuid = file_doc.to_dict().get('file_uuid') # Get UUID from the Firestore document
                blob = self.bucket.blob(file_uuid)
                blob.delete()

                # Delete the file document from Firestore
                file_doc.reference.delete()

            # Delete the collection
            collection_ref.delete()
            return 1
        return 0

    def delete_all(self, user_id: str) -> int:
        user_ref = self.user_collection.document(user_id)
        deleted_count = 0
        for collection_doc in user_ref.collection('collections').stream():
            collection_id = collection_doc.id

            # Get all file references in the collection
            file_refs = collection_doc.reference.collection('files').stream()

            # Delete each file from Cloud Storage
            for file_doc in file_refs:
                file_uuid = file_doc.to_dict().get('file_uuid') # Get UUID from the Firestore document
                blob = self.bucket.blob(file_uuid)
                blob.delete()

                # Delete the file document from Firestore
                file_doc.reference.delete()

            # Delete the collection
            collection_doc.reference.delete()
            deleted_count += 1
        return deleted_count

class FileDBManager:
    def __init__(self) -> None:
        self.db = firestore.client()
        self.user_collection = self.db.collection('users')
        self.bucket = storage.bucket()
        self.collection_manager = CollectionDBManager()

    def add_file(self, file_model: FileModel) -> FileModel:
        user_ref = self.user_collection.document(file_model.user_id)
        collection_ref = user_ref.collection('collections').where("name", "==", file_model.collection_name).get()
        if not collection_ref:
            raise ValueError("Collection not found")

        collection_doc_ref = collection_ref[0].reference

        file_uuid = uuid.uuid4()
        blob = self.bucket.blob(str(file_uuid))
        while blob.exists():
            file_uuid = uuid.uuid4()
            blob = self.bucket.blob(str(file_uuid))

        if file_model.file_bytes:
            blob.upload_from_string(file_model.file_bytes)
        else:
            blob.upload_from_string(b"[]")
    
        file_data = file_model.model_dump(exclude={"file_bytes"})
        file_data['file_uuid'] = str(file_uuid)
        file_ref = collection_doc_ref.collection('files').document(file_model.filename)
        file_ref.set(file_data)
        return file_model
    
    def get_file_ref(self, user_id, collection_name, filename):
        user_ref = self.user_collection.document(user_id)
        if (
            collection_ref := user_ref.collection('collections')
            .where("name", "==", collection_name)
            .get()
        ):
            collection_doc_ref = collection_ref[0].reference
            return collection_doc_ref.collection('files').document(filename)
        return None
    
    def file_exists(self, collection_name: str, user_id: str, filename: str) -> Optional[FileModel]:
        file_ref = self.get_file_ref(user_id, collection_name, filename)
        file_doc = file_ref.get()
        return file_doc.exists

    def get_file_by_name(self, collection_name: str, user_id: str, filename: str) -> Optional[FileModel]:
        file_ref = self.get_file_ref(user_id, collection_name, filename)
        file_doc = file_ref.get()
        if file_doc.exists:
            file_data = file_doc.to_dict()
            blob = self.bucket.blob(file_data['file_uuid'])
            file_data['file_bytes'] = blob.download_as_bytes()
            return FileModel(**file_data)
        return None
    
    def update_file(self, collection_name: str, user_id: str, filename: str, **kwargs: dict) -> int:
        file_ref = self.get_file_ref(user_id, collection_name, filename)
        file_doc = file_ref.get()
        if file_doc.exists:
            file_data = file_doc.to_dict()
            file_uuid = file_data['file_uuid']

            if 'file_bytes' in kwargs and kwargs['file_bytes']:
                blob = self.bucket.blob(file_uuid) # Use the UUID to reference the file in Cloud Storage
                blob.upload_from_string(kwargs['file_bytes'])
                del kwargs['file_bytes']

            file_ref.update(kwargs)
            return 1
        return 0

    def delete_file(self, collection_name: str, user_id: str, filename: str) -> int:
        file_ref = self.get_file_ref(user_id, collection_name, filename)
        file_doc = file_ref.get()
        if file_doc.exists:
            file_uuid = file_doc.to_dict().get('file_uuid')
            blob = self.bucket.blob(file_uuid)
            blob.delete()
            file_ref.delete()
            return 1
        return 0
        
    def get_all_files(self, collection_name: str, user_id: str) -> List[FileModel]:
        files = []
        user_ref = self.user_collection.document(user_id)
        collection_query = user_ref.collection('collections').where("name", "==", collection_name).get()
        if not collection_query:
            return files

        collection_doc_ref = collection_query[0].reference
        files_query = collection_doc_ref.collection('files').stream()
        for file_doc in files_query:
            file_data = file_doc.to_dict()
            files.append(FileModel(**file_data))
        return files
