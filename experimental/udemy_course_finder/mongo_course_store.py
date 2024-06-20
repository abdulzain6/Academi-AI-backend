from pymongo import MongoClient, ASCENDING, UpdateOne
from pymongo.errors import BulkWriteError
from typing import List, Tuple
from datetime import datetime, timedelta
from pydantic import BaseModel
from urllib.parse import urlparse, urlunparse

class Course(BaseModel):
    name: str
    category: str
    image: str | None = None
    actual_price_usd: float
    sale_price_usd: float
    sale_end: datetime
    description: str | None = None
    url: str

def remove_url_parameters(url: str) -> str:
    parsed_url = urlparse(url)
    clean_url = urlunparse(parsed_url._replace(query=""))
    return clean_url

def remove_duplicates(courses: List[Course]) -> List[Course]:
    unique_courses = {}
    for course in courses:
        clean_url = remove_url_parameters(course.url)
        if clean_url not in unique_courses:
            unique_courses[clean_url] = course
    return list(unique_courses.values())

class CourseRepository:
    def __init__(self, uri: str, db_name: str, collection_name: str):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self._create_ttl_index()

    def _create_ttl_index(self):
        # Create TTL index on 'sale_end' field with expireAfterSeconds set to 0
        self.collection.create_index([("sale_end", ASCENDING)], expireAfterSeconds=0)

    def save_courses(self, courses: List[Course]):
        unique_courses = remove_duplicates(courses)
        operations = []
        for course in unique_courses:
            course_dict = course.model_dump()
            clean_url = remove_url_parameters(course.url)
            existing_course = self.collection.find_one({"clean_url": clean_url})
            if existing_course:
                # Update existing course
                operations.append(
                    UpdateOne(
                        {"clean_url": clean_url},
                        {"$set": course_dict}
                    )
                )
            else:
                # Insert new course
                course_dict["clean_url"] = clean_url
                operations.append(
                    UpdateOne(
                        {"clean_url": clean_url},
                        {"$set": course_dict},
                        upsert=True
                    )
                )
        if operations:
            try:
                self.collection.bulk_write(operations, ordered=False)
            except BulkWriteError as e:
                print(f"Bulk write error: {e.details}")

    def search_courses(self, query_str: str, page: int = 1, page_size: int = 10) -> Tuple[List[Course], int]:
        regex_query = {"$or": [
            {"name": {"$regex": query_str, "$options": "i"}},
            {"category": {"$regex": query_str, "$options": "i"}},
            {"description": {"$regex": query_str, "$options": "i"}}
        ]}
        skip = (page - 1) * page_size
        cursor = self.collection.find(regex_query).skip(skip).limit(page_size)
        courses = [Course(**doc) for doc in cursor]
        total = self.collection.count_documents(regex_query)
        return courses, total

    def get_courses(self, page: int = 1, page_size: int = 10) -> Tuple[List[Course], int]:
        skip = (page - 1) * page_size
        cursor = self.collection.find().sort("sale_end", ASCENDING).skip(skip).limit(page_size)
        courses = [Course(**doc) for doc in cursor]
        total = self.collection.count_documents({})
        return courses, total

# Example usage:
if __name__ == "__main__":
    course_repo = CourseRepository(uri="mongodb://root:@localhost:27017", db_name="study-app", collection_name="courses")

    # Adding sample courses
    sample_courses = [
        Course(
            name="Sample Course 1",
            category="Development",
            image=None,
            actual_price_usd=100.0,
            sale_price_usd=10.0,
            sale_end=datetime.utcnow() + timedelta(seconds=30),  # Expires in 30 seconds
            description="This is a sample course 1.",
            url="https://example.com/sample-course-1"
        ),
        Course(
            name="Sample Course 2",
            category="Business",
            image=None,
            actual_price_usd=200.0,
            sale_price_usd=20.0,
            sale_end=datetime(2024, 11, 30, 23, 59, 59),
            description="This is a sample course 2.",
            url="https://example.com/sample-course-2"
        ),
    ]
    course_repo.save_courses(sample_courses)

    # Searching for courses
    courses, total = course_repo.search_courses("sample")
    print(f"Found {total} courses.")
    for course in courses:
        print(course)

    # Getting paginated courses
    courses, total = course_repo.get_courses(page=1, page_size=5)
    print(f"Found {total} courses.")
    for course in courses:
        print(course)
