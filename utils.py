def list_viruses(virus_definitions):
    print("Current virus definitions:")
    for virus in virus_definitions:
        print(virus)

def add_virus(virus_definitions, new_virus):
    if new_virus not in virus_definitions:
        virus_definitions.append(new_virus)
        print(f"Added new virus definition: {new_virus}")
    else:
        print("Virus definition already exists.")

def remove_virus(virus_definitions, virus_to_remove):
    if virus_to_remove in virus_definitions:
        virus_definitions.remove(virus_to_remove)
        print(f"Removed virus definition: {virus_to_remove}")
    else:
        print("virus definition not found.")
