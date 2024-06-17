from pymongo import MongoClient
from datetime import datetime

def get_logs_after_date(db_name: str, collection_name: str, date: datetime):
    # Connect to MongoDB
    client = MongoClient('mongodb://root:pdCHU4f7tF@localhost:27017')  # Adjust the connection string if needed
    db = client[db_name]
    collection = db[collection_name]

    # Filter logs using the datetime value
    query = {
        "timestamp": {
            "$gt": date
        }
    }

    # Execute the query
    results = collection.find(query)

    # Print the results
    for log in results:
        print(log["message"], log["timestamp"])

# Parameters
db_name = "study-app"
collection_name = "logs"
date = datetime(2024, 6, 7)

# Get logs after the specified date
get_logs_after_date(db_name, collection_name, date)
