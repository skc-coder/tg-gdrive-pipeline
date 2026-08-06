import os
import shutil
import re

BASE_DIR = "/home/skc/Downloads/algorithms"

# Exact ordered module structure with numbers 01 to 16
NUMBERED_MODULES = [
    ("01", "Why Study Algorithms"),
    ("02", "Asymptotic Analysis and Loop Complexities (DS Course Videos)"),
    ("03", "Time Complexity of Recursive Programs"),
    ("04", "Divide and Conquer Algorithms (Part-1)"),
    ("05", "Maximum and Minimum Of Numbers"),
    ("06", "Divide and Conquer Algorithms (Part-2)"),
    ("07", "Sorting Algorithms (selection, insertion, bubble, counting sort)"),
    ("08", "Breadth First and Depth First search (BFS and DFS)"),
    ("09", "Shortest Paths Algorithms (Greedy Algorithms)"),
    ("10", "Minimum Spanning Tree Algorithms (Greedy Algorithms)"),
    ("11", "More Greedy Algorithms"),
    ("12", "Dynamic Programming"),
    ("13", "More Dynamic Programming Algorithms"),
    ("14", "Revision and Practice Sessions"),
    ("15", "Students' Hand Written Notes"),
    ("16", "LIVE Sessions")
]

# Patterns to match filenames to module index
RULES = [
    (r"Why Study Algorithms", "01"),
    (r"Asymptotic Analysis", "02"),
    (r"Time Complexity of Recursive Programs", "03"),
    (r"Divide and Conquer Algorithms \(Part-1\)", "04"),
    (r"Maximum and Minimum Of Numbers|Maximum_and_Minimum_Of_Numbers", "05"),
    (r"Divide and Conquer Algorithms \(Part-2\)", "06"),
    (r"Sorting Algorithms", "07"),
    (r"Breadth First and Depth First search", "08"),
    (r"Shortest Paths Algorithms", "09"),
    (r"Minimum Spanning Tree Algorithms", "10"),
    (r"More Greedy Algorithms", "11"),
    (r"More Dynamic Programming Algorithms", "13"),
    (r"Dynamic Programming", "12"),
    (r"Revision and Practice Sessions", "14"),
    (r"Students Hand Written Notes|Students' Hand Written Notes|HandWritten Notes|Quantum City|Karan Agrawal|Himanshu Dutta|Mahek Garala|Shaikh Hasib|Rich Amrutiya", "15"),
    (r"LIVE Sessions", "16"),
]

def organize_numbered():
    # Create index to folder name mapping
    folder_map = {}
    for num, title in NUMBERED_MODULES:
        folder_name = f"Module {num} - {title}"
        folder_map[num] = folder_name
        os.makedirs(os.path.join(BASE_DIR, folder_name), exist_ok=True)

    # Collect all valid files
    all_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for f in files:
            if f.endswith(".crdownload") or f.endswith(".tmp") or f.endswith(".part"):
                continue
            all_files.append(os.path.join(root, f))

    print(f"Total files found: {len(all_files)}")

    moved_count = 0
    for file_path in all_files:
        filename = os.path.basename(file_path)
        matched_num = None

        for pattern, num in RULES:
            if re.search(pattern, filename, re.IGNORECASE) or re.search(pattern, file_path, re.IGNORECASE):
                matched_num = num
                break

        if matched_num:
            target_folder_name = folder_map[matched_num]
            dest_dir = os.path.join(BASE_DIR, target_folder_name)
            dest_path = os.path.join(dest_dir, filename)

            if os.path.abspath(file_path) != os.path.abspath(dest_path):
                shutil.move(file_path, dest_path)
                moved_count += 1
                print(f"Moved: '{filename}' -> '{target_folder_name}/'")

    print(f"\nMoved {moved_count} files.")

    # Remove any old unnumbered directories
    valid_dirs = set(folder_map.values())
    for item in os.listdir(BASE_DIR):
        item_path = os.path.join(BASE_DIR, item)
        if os.path.isdir(item_path) and item not in valid_dirs:
            shutil.rmtree(item_path, ignore_errors=True)
            print(f"Removed old folder: {item}")

if __name__ == '__main__':
    organize_numbered()
