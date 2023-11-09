from random import sample

def select_random_chunks(text: str, chunk_size: int, total_length: int) -> str:
    if len(text) <= chunk_size:
        return text

    # Split the text into chunks
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    # Calculate the number of chunks needed to meet the 'total_length'
    num_chunks_needed = min(len(chunks), total_length // chunk_size)

    # Pick random unique chunks
    selected_indices = sample(range(len(chunks)), num_chunks_needed)
    selected_indices.sort()  # Sort the indices to maintain original order

    # Concatenate the selected chunks to form the output string
    selected_chunks = [chunks[i] for i in selected_indices]
    return ''.join(selected_chunks)[:total_length]