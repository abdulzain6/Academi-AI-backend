import logging
from globals import firebase_admin
from lib.database import UserDBManager, UserModel, CollectionDBManager, CollectionModel, FileDBManager, FileModel
import unittest


class TestUserDBManager(unittest.TestCase):
    def setUp(self):
        self.user_db_manager = UserDBManager()
        self.user_db_manager.delete_user("123")
        
    def test_add_and_get_user(self):
        user_model = UserModel(uid="123", email="test@example.com")
        added_user = self.user_db_manager.add_user(user_model)

        self.assertEqual(added_user.uid, "123")
        self.assertEqual(added_user.email, "test@example.com")

        retrieved_user = self.user_db_manager.get_user_by_uid("123")
        self.assertEqual(retrieved_user.uid, "123")
        self.assertEqual(retrieved_user.email, "test@example.com")

    def test_update_user(self):
        # Adding the user before updating
        user_model = UserModel(uid="123", email="original@example.com")
        self.user_db_manager.add_user(user_model)

        # Updating the email of the user
        self.user_db_manager.update_user(uid="123", email="updated@example.com")
        updated_user = self.user_db_manager.get_user_by_uid("123")

        self.assertIsNotNone(updated_user, "User not found in the database")
        self.assertEqual(updated_user.email, "updated@example.com")


    def test_delete_user(self):
        self.user_db_manager.delete_user(uid="123")
        deleted_user = self.user_db_manager.get_user_by_uid("123")
        self.assertIsNone(deleted_user)

    def test_insert_many(self):
        users = [UserModel(uid=str(i), email=f"user{i}@example.com") for i in range(5)]
        self.user_db_manager.insert_many(users)

        all_users = self.user_db_manager.get_all()
        self.assertEqual(len(all_users), 5)
           

class TestCollectionDBManager(unittest.TestCase):
    def setUp(self):
        try:
            user_model = UserModel(uid="123", email="test@example.com")
            user_db_manager = UserDBManager()
            added_user = user_db_manager.add_user(user_model)
        except:
            ...
        
        self.collection_db_manager = CollectionDBManager()
        self.sample_user_id = "123"  # Replace with actual user UID
        self.sample_collection = CollectionModel(
            user_uid=self.sample_user_id,
            name="Test Collection",
            description="A test collection"
        )
        self.collection_db_manager.delete_collection(self.sample_user_id, "Test Collection")

    def test_add_collection(self):
        self.collection_db_manager.delete_collection(self.sample_user_id, "Test Collection")
        collection_model = self.collection_db_manager.add_collection(self.sample_collection)
        coll = self.collection_db_manager.get_collection_by_name_and_user('Test Collection', self.sample_user_id)
        logging.info(f"Added collection, {coll}")
        self.assertEqual(collection_model.name, "Test Collection")

    def test_get_collection_by_name_and_user(self):
        self.collection_db_manager.add_collection(self.sample_collection)
        collection_model = self.collection_db_manager.get_collection_by_name_and_user("Test Collection", self.sample_user_id)
        self.assertIsNotNone(collection_model)
        self.assertEqual(collection_model.name, "Test Collection")

    def test_get_all_by_user(self):
        self.collection_db_manager.add_collection(self.sample_collection)
        collections = self.collection_db_manager.get_all_by_user(self.sample_user_id)
        self.assertGreater(len(collections), 0)

    def test_update_collection(self):
        try:
            self.collection_db_manager.add_collection(self.sample_collection)
        except:
            ...
        updated = self.collection_db_manager.update_collection(self.sample_user_id, "Test Collection", description="Updated description")
        self.assertEqual(updated, 1)

    def test_delete_collection(self):
        self.collection_db_manager.add_collection(self.sample_collection)
        deleted = self.collection_db_manager.delete_collection(self.sample_user_id, "Test Collection")
        self.assertEqual(deleted, 1)

    def test_delete_all(self):
        self.collection_db_manager.add_collection(self.sample_collection)
        deleted_count = self.collection_db_manager.delete_all("123")
        self.assertGreaterEqual(deleted_count, 1)

    def tearDown(self):
        # Cleanup: Delete test data
        self.collection_db_manager.delete_collection(self.sample_user_id, "Test Collection")


class TestFileDBManager(unittest.TestCase):
    def setUp(self):
        self.sample_user_id = "123"  # Replace with actual user UID
        self.sample_collection_name = "Test Collection"
        self.sample_filename = "test_file.txt"
        try:
            user_db_manager = UserDBManager()
            user_model = UserModel(uid="123", email="test@example.com")
            added_user = user_db_manager.add_user(user_model)
        except:
            ...
            
        try:
            coll = CollectionModel(
                user_uid=self.sample_user_id,
                name="Test Collection",
                description="A test collection"
            )
            coll_manager = CollectionDBManager()
            coll_manager.add_collection(coll)
            logging.info(coll_manager.get_all_by_user(self.sample_user_id))
        except:
            ...
            
        self.file_db_manager = FileDBManager()
        self.sample_file_model = FileModel(
            collection_name=self.sample_collection_name,
            user_id=self.sample_user_id,
            filename=self.sample_filename,
            description="A test file",
            file_bytes=b"Sample content"
        )

        # Cleanup: Delete any existing test file
        self.file_db_manager.delete_file(self.sample_collection_name, self.sample_user_id, self.sample_filename)

    def test_add_file(self):
        result = self.file_db_manager.add_file(self.sample_file_model)
        self.assertEqual(result.filename, self.sample_file_model.filename)

    def test_get_file_by_name(self):
        self.file_db_manager.add_file(self.sample_file_model)
        result = self.file_db_manager.get_file_by_name(self.sample_collection_name, self.sample_user_id, self.sample_filename)
        self.assertEqual(result.filename, self.sample_file_model.filename)

    def test_update_file(self):
        self.file_db_manager.add_file(self.sample_file_model)
        update_result = self.file_db_manager.update_file(self.sample_collection_name, self.sample_user_id, self.sample_filename, description="Updated description")
        self.assertEqual(update_result, 1)
        result = self.file_db_manager.get_file_by_name(self.sample_collection_name, self.sample_user_id, self.sample_filename)
        self.assertEqual(result.description, "Updated description")

    def test_delete_file(self):
        self.file_db_manager.add_file(self.sample_file_model)
        delete_result = self.file_db_manager.delete_file(self.sample_collection_name, self.sample_user_id, self.sample_filename)
        self.assertEqual(delete_result, 1)
        result = self.file_db_manager.get_file_by_name(self.sample_collection_name, self.sample_user_id, self.sample_filename)
        self.assertIsNone(result)

    def test_get_all_files(self):
        self.file_db_manager.add_file(self.sample_file_model)
        result = self.file_db_manager.get_all_files(self.sample_collection_name, self.sample_user_id)
        logging.info(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].filename, self.sample_file_model.filename)

    def tearDown(self):
        # Cleanup: Delete test data
        self.file_db_manager.delete_file(self.sample_collection_name, self.sample_user_id, self.sample_filename)



        
if __name__ == "__main__":
    unittest.main()