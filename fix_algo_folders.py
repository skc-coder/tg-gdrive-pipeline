import os
import shutil
import re

BASE_DIR = "/home/skc/Downloads/algorithms"

# New folder structure requested by the user
NEW_FOLDERS = [
    "Why Study Algorithms",
    "Asymptotic Analysis and Loop Complexities (DS Course Videos)",
    "Time Complexity of Recursive Programs",
    "Divide and Conquer Algorithms (Part-1)",
    "Maximum and Minimum Of Numbers",
    "Divide and Conquer Algorithms (Part-2)",
    "Sorting Algorithms (selection, insertion, bubble, counting sort)",
    "Breadth First and Depth First search (BFS and DFS)",
    "Shortest Paths Algorithms (Greedy Algorithms)",
    "Minimum Spanning Tree Algorithms (Greedy Algorithms)",
    "More Greedy Algorithms",
    "Dynamic Programming",
    "More Dynamic Programming Algorithms",
    "Revision and Practice Sessions",
    "Students' Hand Written Notes",
    "LIVE Sessions"
]

# Mapping rules from filename prefix/content to target folder
RULES = [
    (r"Why Study Algorithms", "Why Study Algorithms"),
    (r"Asymptotic Analysis", "Asymptotic Analysis and Loop Complexities (DS Course Videos)"),
    (r"Time Complexity of Recursive Programs", "Time Complexity of Recursive Programs"),
    (r"Divide and Conquer Algorithms \(Part-1\)", "Divide and Conquer Algorithms (Part-1)"),
    (r"Maximum and Minimum Of Numbers|Maximum_and_Minimum_Of_Numbers", "Maximum and Minimum Of Numbers"),
    (r"Divide and Conquer Algorithms \(Part-2\)", "Divide and Conquer Algorithms (Part-2)"),
    (r"Sorting Algorithms", "Sorting Algorithms (selection, insertion, bubble, counting sort)"),
    (r"Breadth First and Depth First search", "Breadth First and Depth First search (BFS and DFS)"),
    (r"Shortest Paths Algorithms", "Shortest Paths Algorithms (Greedy Algorithms)"),
    (r"Minimum Spanning Tree Algorithms", "Minimum Spanning Tree Algorithms (Greedy Algorithms)"),
    (r"More Greedy Algorithms", "More Greedy Algorithms"),
    (r"More Dynamic Programming Algorithms", "More Dynamic Programming Algorithms"),
    (r"Dynamic Programming", "Dynamic Programming"),
    (r"Revision and Practice Sessions", "Revision and Practice Sessions"),
    (r"Students Hand Written Notes|Students' Hand Written Notes|HandWritten Notes|Quantum City|Karan Agrawal|Himanshu Dutta|Mahek Garala|Shaikh Hasib|Rich Amrutiya", "Students' Hand Written Notes"),
    (r"LIVE Sessions", "LIVE Sessions"),
]

def clean_up_and_reorganize():
    # Step 1: Collect all files across root and subfolders (exclude downloading files)
    all_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for f in files:
            if f.endswith(".crdownload") or f.endswith(".tmp") or f.endswith(".part"):
                continue
            all_files.append(os.path.join(root, f))

    print(f"Total valid files found to organize: {len(all_files)}")

    # Step 2: Create new clean top-level directories
    for folder in NEW_FOLDERS:
        os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

    # Step 3: Move files to the correct target folder
    moved_count = 0
    unmatched = []

    for file_path in all_files:
        filename = os.path.basename(file_path)
        target_folder = None

        for pattern, folder in RULES:
            if re.search(pattern, filename, re.IGNORECASE) or re.search(pattern, file_path, re.IGNORECASE):
                target_folder = folder
                break

        if target_folder:
            dest_dir = os.path.join(BASE_DIR, target_folder)
            dest_path = os.path.join(dest_dir, filename)
            
            # Avoid moving onto itself
            if os.path.abspath(file_path) != os.path.abspath(dest_path):
                shutil.move(file_path, dest_path)
                moved_count += 1
                print(f"Moved: '{filename}' -> '{target_folder}/'")
        else:
            unmatched.append(file_path)

    print(f"\nMoved {moved_count} files.")
    if unmatched:
        print(f"Unmatched files ({len(unmatched)}):")
        for u in unmatched:
            print("  ", u)

    # Step 4: Remove any empty or old unused directories (keep only NEW_FOLDERS and root .crdownload files)
    for item in os.listdir(BASE_DIR):
        item_path = os.path.join(BASE_DIR, item)
        if os.path.isdir(item_path) and item not in NEW_FOLDERS:
            # Delete old directory if empty or containing no valid files
            shutil.rmtree(item_path, ignore_errors=True)
            print(f"Removed old directory: {item}")

if __name__ == '__main__':
    clean_up_and_reorganize()
