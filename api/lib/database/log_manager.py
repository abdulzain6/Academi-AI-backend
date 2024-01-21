from pymongo import MongoClient
from pymongo.collection import Collection
import logging
import datetime

class MongoLogManager:
    def __init__(self, uri: str, db_name: str, collection_name: str):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection: Collection = self.db[collection_name]

    def insert_log(self, message: str, level: str):
        log_entry = {
            "message": message,
            "level": level,
            "timestamp": datetime.datetime.now()
        }
        self.collection.insert_one(log_entry)

    def info(self, message: str):
        self.insert_log(message, "INFO")
        logging.info(message)

    def warning(self, message: str):
        self.insert_log(message, "WARNING")
        logging.warning(message)

    def error(self, message: str):
        self.insert_log(message, "ERROR")
        logging.error(message)