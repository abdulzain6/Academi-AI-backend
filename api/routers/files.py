import logging
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi import Depends, HTTPException, status
from ..globals import collection_manager, knowledge_manager, file_manager, subscription_manager
from ..lib.database.files import FileModel
from ..lib.database.purchases import SubscriptionType
from ..lib.utils import get_file_extension, format_url, convert_youtube_url_to_standard
from pydantic import BaseModel
from typing import Optional
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import can_add_more_data


router = APIRouter()

MAX_FILE_SIZE = 25 * 1024 * 1024


class FileCreate(BaseModel):
    collection_name: str
    description: str
    file: UploadFile


class FileDelete(BaseModel):
    collection_name: str
    file_name: str


class LinkFileInput(BaseModel):
    collection_name: str
    filename: str
    description: Optional[str] = ""
    youtube_link: Optional[str]
    web_link: Optional[str]


def is_safe_filename(filename: str) -> bool:
    """
    Check if the filename is safe to use.
    """
    return not any(seg in ["..", "/"] for seg in os.path.split(filename))


@router.post("/linkfile")
def create_link_file(
    linkfile: LinkFileInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    can_add_more_data(user_id, linkfile.collection_name, collection_check=False)
    
    logging.info(f"Create linkfile request from {user_id}, input: {linkfile}")
    linkfile.youtube_link = convert_youtube_url_to_standard(
        format_url(linkfile.youtube_link)
    )
    linkfile.web_link = format_url(linkfile.web_link)
    logging.info(f"Fixing url for {user_id}")


    collection = collection_manager.get_collection_by_name_and_user(
        linkfile.collection_name, user_id
    )
    logging.info(f"Collection: {collection}")
    if not collection:
        logging.error(f"Collection does not exist. {user_id}")
        raise HTTPException(detail="Collection does not exist", status_code=404)

    if not linkfile.youtube_link and not linkfile.web_link:
        raise HTTPException(
            detail="Either weburl or youtube_link must be specified",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if linkfile.youtube_link and linkfile.web_link:
        raise HTTPException(
            detail="Either weburl or youtube_link must be specified. Not both.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if file_manager.file_exists(user_id, collection.collection_uid, linkfile.filename):
        logging.error(f"File already exists {user_id}")
        raise HTTPException(
            detail="File Already exists", status_code=status.HTTP_400_BAD_REQUEST
        )

    extension = ".yt" if linkfile.youtube_link else ".html"

    try:
        logging.info("Started loading")
        contents, ids, file_bytes = knowledge_manager.load_web_youtube_link(
            metadata={"file": linkfile.filename, "collection" : collection.name, "user" : user_id},
            youtube_link=linkfile.youtube_link,
            web_url=linkfile.web_link,
        )
    except Exception as e:
        import traceback
        logging.error(f"File not supported, Error: {traceback.format_exception(e)}")
        raise HTTPException(400, "Link has no data/ Invalid link") from e

    try:
        file_model = file_manager.add_file(
            FileModel(
                friendly_filename=linkfile.filename,
                collection_name=linkfile.collection_name,
                user_id=user_id,
                filename=linkfile.filename,
                description=linkfile.description,
                file_content=contents,
                file_bytes=file_bytes,
                vector_ids=ids,
                filetype=extension,
            ),
        )
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=400)
    
    logging.info(f"File created, File name: {file_model.filename}, Collection: {linkfile.collection_name} {user_id}")
    return {
        "status": "success",
        "file": {
            "collection_name": linkfile.collection_name,
            "filename": file_model.filename,
            "description": file_model.description,
            "filetype": file_model.filetype,
            "friendly_name": file_model.friendly_filename,
        },
    }


@router.post("/")
def create_file(
    collection_name: str,
    filename: str,
    description: str = "",
    file: UploadFile = File(...),
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    can_add_more_data(user_id, collection_name, collection_check=False)
    
    try:
        logging.info(f"Create file request from {user_id}, collection={collection_name}, filename={filename}")
        if not is_safe_filename(filename) or not is_safe_filename(file.filename):
            logging.warning(f"{user_id} is a sus user!")
            raise HTTPException(
                detail="Invalid filename", status_code=status.HTTP_400_BAD_REQUEST
            )

        collection = collection_manager.get_collection_by_name_and_user(
            collection_name, user_id
        )
        if not collection:
            logging.error(f"Collection does not exist {user_id}")
            raise HTTPException(detail="Collection does not exist", status_code=404)

        if file_manager.file_exists(user_id, collection.collection_uid, filename):
            logging.error(f"File already exists {user_id}")
            raise HTTPException(
                detail="File Already exists", status_code=status.HTTP_400_BAD_REQUEST
            )
            
        # Check file size before reading it completely
        file_size = file.file.seek(0, os.SEEK_END)
        file.file.seek(0)  # Reset file pointer to the beginning
        if file_size > MAX_FILE_SIZE:
            logging.error(f"File is too big {user_id}")
            raise HTTPException(
                status_code=400,
                detail="File size exceeds the maximum limit",
            )

        user_plan = subscription_manager.get_subscription_type(user_id)
        if user_plan in {SubscriptionType.PRO, SubscriptionType.ELITE}:
            advanced_extraction = True
        else:
            advanced_extraction = False
            
        logging.info(f"Advanced extraction : {advanced_extraction}, User plan : {user_plan}, uid: {user_id}")
            
        _, file_extension = os.path.splitext(file.filename)

        # Create a secure temporary file with the same extension
        with tempfile.NamedTemporaryFile(
            delete=True, suffix=file_extension, mode="w+b"
        ) as temp_file:
            contents = file.file.read()
            temp_file.write(contents)
            temp_file.seek(0)

            try:
                contents, ids, file_bytes = knowledge_manager.load_and_injest_file(
                    temp_file.name,
                    {"file": filename, "collection" : collection.name, "user" : user_id},
                    advanced_pdf_extraction=advanced_extraction
                )
            except Exception as e:
                import traceback
                logging.error(f"File not supported, Error: {traceback.format_exception(e)}")
                raise HTTPException(400, "FIle not supported/ FIle has no Data") from e

            try:
                file_model = file_manager.add_file(
                    FileModel(
                        friendly_filename=filename,
                        collection_name=collection_name,
                        filename=filename,
                        description=description,
                        file_content=contents,
                        file_bytes=file_bytes,
                        vector_ids=ids,
                        filetype=get_file_extension(file.filename),
                        user_id=user_id,
                    ),
                )
            except Exception as e:
                raise HTTPException(detail=str(e), status_code=400)
            
        logging.info(f"File created, File name: {file_model.filename}, Collection: {collection_name} {user_id}")
        return {
            "status": "success",
            "file": {
                "collection_name": collection_name,
                "filename": file_model.filename,
                "description": file_model.description,
                "filetype": file_model.filetype,
                "friendly_name": file_model.friendly_filename,
            },
        }
    finally:
        file.file.close()


@router.get("/")
def get_file(
    collection_name: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Get file request {user_id}")
    if not collection_manager.get_collection_by_name_and_user(collection_name, user_id):
        logging.error(f"Collection {collection_name} does not exist, {user_id}")
        raise HTTPException(detail="Collection does not exist", status_code=404)

    files = file_manager.get_all_files(user_id, collection_name)    
    files_response = [
        {
            "collection_name": collection_name,
            "filename": file.filename,
            "description": file.description,
            "filetype": file.filetype,
            "friendly_name": file.friendly_filename,
        }
        for file in files
    ]
    logging.info(f"Files got successfully, {user_id}")
    return {"status": "success", "files": files_response}


@router.get("/{file_name}")
def get_file(
    collection_name: str,
    file_name: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got get file by name request, {user_id}... File: {file_name} Collection: {collection_name}")
    if not collection_manager.collection_exists(collection_name, user_id):
        logging.error(f"Collection {collection_name} does not exist, {user_id}")
        raise HTTPException(detail="Collection does not exist", status_code=404)

    if file := file_manager.get_file_by_name(
        collection_name=collection_name, filename=file_name, user_id=user_id
    ):
        logging.info(f"File {file_name} got successfully, {user_id}")
        return {
            "file": {
                "collection_name": collection_name,
                "filename": file.filename,
                "description": file.description,
                "filetype": file.filetype,
                "friendly_name": file.friendly_filename,
            }
        }
    logging.error(f"File does not exist, {user_id}")
    raise HTTPException(detail="File does not exist", status_code=404)


@router.delete("/")
def delete_file(
    collection_name: str,
    file_name: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got delete file by name request, {user_id}... File: {file_name} Collection: {collection_name}")

    collection = collection_manager.get_collection_by_name_and_user(
        collection_name, user_id
    )
    if not collection:
        logging.error(f"Collection {collection_name} does not exist, {user_id}")
        raise HTTPException(detail="Collection does not exist", status_code=404)

    if not file_manager.file_exists(
        collection_uid=collection.collection_uid, filename=file_name, user_id=user_id
    ):
        logging.error(f"File does not exist, {user_id}")
        raise HTTPException(detail="File does not exist", status_code=404)

    file = file_manager.get_file_by_name(
        collection_name=collection_name, filename=file_name, user_id=user_id
    )
    logging.info(f"Deleting ids, {user_id}")
    knowledge_manager.delete_ids(ids=file.vector_ids)
    success = file_manager.delete_file(
        collection_name=collection_name,
        filename=file_name,
        user_id=user_id,
    )
    logging.info(f"File {file_name} deleted successfully, {user_id}")
    return {"status": "success", "error": "", "code": success}


@router.get("/{file_name}/download")
def download_file(
    collection_name: str,
    file_name: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got download file by name request, {user_id}... File: {file_name} Collection: {collection_name}")

    if not collection_manager.collection_exists(collection_name, user_id):
        logging.error(f"Collection {collection_name} does not exist, {user_id}")
        raise HTTPException(detail="Collection does not exist", status_code=404)

    if file := file_manager.get_file_by_name(
        collection_name=collection_name, filename=file_name, user_id=user_id, bytes=True
    ):
        with tempfile.NamedTemporaryFile(
            delete=False, prefix=file.friendly_filename, suffix=file.filetype
        ) as temp_file:
            temp_file.write(file.file_bytes)
            logging.info(f"File sending soon! {user_id}")
            return FileResponse(
                temp_file.name,
                headers={
                    "Content-Disposition": f"attachment; filename={temp_file.name}"
                },
            )
    else:
        logging.error(f"File does not {user_id}")
        raise HTTPException(detail="File does not exist", status_code=404)
