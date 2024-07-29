import os
import re
from utils import remove_virus


def scan_folder(folder_path, virus_definitions):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                    for virus in virus_definitions:
                        if re.search(virus.encode(), file_content, re.IGNORECASE):
                            print(f"Virus detected: {virus} in {file_path}")
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")


def delete_virus(folder_path, virus_definitions):
    updated_definitions = list(virus_definitions)  # Create a copy to modify
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    file_content = f.read()

                file_modified = False
                for virus in virus_definitions:
                    if re.search(virus.encode(), file_content, re.IGNORECASE):
                        print(f"Virus detected: {virus} in {file_path}")
                        cleaned_content = file_content.replace(virus.encode(), b"")
                        with open(file_path, 'wb') as f:
                            f.write(cleaned_content)
                        print(f"Virus removed: {virus} from {file_path}")
                        file_modified = True

                if file_modified:
                    # Ensure virus is in the list if it was just found
                    if virus not in updated_definitions:
                        updated_definitions.append(virus)

            except Exception as e:
                print(f"Error removing virus from {file_path}: {e}")

    # Remove viruses that were not found during this scan
    for virus in virus_definitions:
        if virus not in updated_definitions:
            remove_virus(updated_definitions, virus)

    return updated_definitions
