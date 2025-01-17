import csv
from pymongo import MongoClient

client = MongoClient('mongodb://root:pdCHU4f7tF@localhost:27017')
db = client['study-app']
users = db['users']
locations = db['locations']

user_docs = list(users.find())
user_ids = [user.get('uid') for user in user_docs]
location_docs = list(locations.find({'user_id': {'$in': user_ids}}))

location_map = {loc['user_id']: loc for loc in location_docs}

with open('user_data.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['Email', 'Country', 'City'])
    
    for user in user_docs:
        email = user.get('email')
        location = location_map.get(user.get('uid'))
        country = location.get('country') if location else None 
        city = location.get('city') if location else None
        writer.writerow([email, country, city])

client.close()
