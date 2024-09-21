import sys
import os
from scan import scan_folder, delete_virus
from virus_definitions import load_virus_definitions, save_virus_definitions
from utils import list_viruses, add_virus, remove_virus

VERSION = "vr1.0.2"

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python antivirus.py [command] [options]")
        print(f"antivirus {VERSION}")
        print("Commands:")
        print("  scan [folder_path] - Scan the specified folder")
        print("  list - List current virus definitions")
        print("  add [virus_signature] - Add a new virus definition")
        print("  remove [virus_signature] - Remove a virus definition")
        print("  delete [folder_path] - Delete detected viruses from the specified folder")
        return

    command = sys.argv[1]

    if command == "scan":
        if len(sys.argv) != 3:
            print("Usage: python antivirus.py scan [folder_path]")
            return
        folder_path = sys.argv[2]
        virus_definitions = load_virus_definitions()
        scan_folder(folder_path, virus_definitions)

    elif command == "list":
        virus_definitions = load_virus_definitions()
        list_viruses(virus_definitions)

    elif command == "add":
        if len(sys.argv) != 3:
            print("Usage: python antivirus.py add [virus_signature]")
            return
        new_virus = sys.argv[2]
        virus_definitions = load_virus_definitions()
        add_virus(virus_definitions, new_virus)
        save_virus_definitions(virus_definitions)

    elif command == "remove":
        if len(sys.argv) != 3:
            print("Usage: python antivirus.py remove [virus_signature]")
            return
        virus_to_remove = sys.argv[2]
        virus_definitions = load_virus_definitions()
        remove_virus(virus_definitions, virus_to_remove)
        save_virus_definitions(virus_definitions)

    elif command == "delete":
        if len(sys.argv) != 3:
            print("Usage: python antivirus.py delete [folder_path]")
            return
        folder_path = sys.argv[2]
        virus_definitions = load_virus_definitions()
        updated_definitions = delete_virus(folder_path, virus_definitions)
        save_virus_definitions(updated_definitions)

    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
#fuck have no more idea

