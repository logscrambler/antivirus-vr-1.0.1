import os

VIRUS_DB_PATH = 'virus_db.txt'

def load_virus_definitions():
    if not os.path.exists(VIRUS_DB_PATH):
        return []
    with open(VIRUS_DB_PATH, 'r') as f:
        return [line.strip() for line in f]

def save_virus_definitions(virus_definitions):
    with open(VIRUS_DB_PATH, 'w') as f:
        for virus in virus_definitions:
            f.write(f"{virus}\n")
#fuck I have no idea
