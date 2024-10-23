import uuid
from pymongo import MongoClient
from bson import ObjectId
from gridfs import GridFS
from typing import Optional, BinaryIO, List
import datetime
from pydantic import BaseModel, Field
from enum import Enum

class LectureStatus(str, Enum):
    READY = "READY"
    PENDING = "PENDING"
    FAILED = "FAILED"

class LectureCreate(BaseModel):
    user_id: str
    topic: str
    instructions: str

class LectureUpdate(BaseModel):
    topic: Optional[str] = None
    instructions: Optional[str] = None
    status: Optional[LectureStatus] = None

class LectureResponse(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    topic: str
    instructions: str
    status: LectureStatus
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

class LectureDB:
    def __init__(self, connection_string: str, database_name: str):
        self.client: MongoClient = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.lectures = self.db.lectures
        self.fs: GridFS = GridFS(self.db)

    def create_lecture(self, lecture: LectureCreate, video_file: BinaryIO, ppt_file: BinaryIO) -> str:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        video_id = self.fs.put(video_file, filename=f"{lecture.topic}_{timestamp}_{uuid.uuid4()}_video")
        ppt_id = self.fs.put(ppt_file, filename=f"{lecture.topic}_{timestamp}_{uuid.uuid4()}_ppt")

        lecture_dict = lecture.model_dump()
        lecture_dict.update({
            "video_file_id": video_id,
            "ppt_file_id": ppt_id,
            "created_at": datetime.datetime.now(),
            "status": LectureStatus.PENDING
        })

        return str(self.lectures.insert_one(lecture_dict).inserted_id)

    def get_lecture(self, lecture_id: str) -> Optional[LectureResponse]:
        lecture = self.lectures.find_one({"_id": ObjectId(lecture_id)})
        if lecture:
            lecture["_id"] = str(lecture["_id"])
            return LectureResponse(**lecture)
        return None

    def update_lecture(self, lecture_id: str, lecture_update: LectureUpdate, 
                       video_file: Optional[BinaryIO] = None, 
                       ppt_file: Optional[BinaryIO] = None) -> bool:
        update_data = lecture_update.dict(exclude_unset=True)
        lecture = self.lectures.find_one({"_id": ObjectId(lecture_id)})
        if not lecture:
            return False

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        if video_file:
            self.fs.delete(lecture["video_file_id"])
            new_video_id = self.fs.put(video_file, filename=f"{update_data.get('topic', lecture['topic'])}_{timestamp}_video")
            update_data["video_file_id"] = new_video_id

        if ppt_file:
            self.fs.delete(lecture["ppt_file_id"])
            new_ppt_id = self.fs.put(ppt_file, filename=f"{update_data.get('topic', lecture['topic'])}_{timestamp}_ppt")
            update_data["ppt_file_id"] = new_ppt_id

        if update_data:
            update_data["updated_at"] = datetime.datetime.now()
            self.lectures.update_one({"_id": ObjectId(lecture_id)}, {"$set": update_data})
            return True
        return False

    def delete_lecture(self, lecture_id: str) -> bool:
        lecture = self.lectures.find_one({"_id": ObjectId(lecture_id)})
        if lecture:
            self.fs.delete(lecture["video_file_id"])
            self.fs.delete(lecture["ppt_file_id"])
            self.lectures.delete_one({"_id": ObjectId(lecture_id)})
            return True
        return False

    def get_user_lectures(self, user_id: str) -> List[LectureResponse]:
        user_lectures = list(self.lectures.find({"user_id": user_id}))
        return [LectureResponse(**{**lecture, "_id": str(lecture["_id"])}) for lecture in user_lectures]

    def get_file(self, file_id: ObjectId) -> Optional[GridFS]:
        return self.fs.get(file_id)

    def download_video(self, lecture_id: str) -> Optional[bytes]:
        lecture = self.lectures.find_one({"_id": ObjectId(lecture_id)})
        if lecture and "video_file_id" in lecture:
            video_file = self.fs.get(lecture["video_file_id"])
            return video_file.read()
        return None

    def download_ppt(self, lecture_id: str) -> Optional[bytes]:
        lecture = self.lectures.find_one({"_id": ObjectId(lecture_id)})
        if lecture and "ppt_file_id" in lecture:
            ppt_file = self.fs.get(lecture["ppt_file_id"])
            return ppt_file.read()
        return None

    def close(self) -> None:
        self.client.close()