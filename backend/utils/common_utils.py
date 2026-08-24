import os

def get_directory_size(path: str) -> int:
    total_size = 0
    for dirpath, __, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size