import os


def get_file_extension(file_path: str):
    return os.path.splitext(file_path)[1]

def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]