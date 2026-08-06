import os
import shutil
import re

BASE_DIR = "/home/skc/Downloads/algorithms"

# Define mapping rules: pattern keywords -> target subfolder path relative to BASE_DIR
RULES = [
    # Students' Hand Written Notes
    (r"Quantum City|Himanshu Dutta|Mahek Garala|Hand Written Notes|Students Hand Written Notes", "Students' Hand Written Notes/Handwritten Notes"),
    
    # Module: Floating Point Representation
    (r"Fixed Point", "Module: Floating Point Representation/Lecture 1 - Fixed Point Representation"),
    (r"Denorm|Denorms|Floating Point", "Module: Floating Point Representation/Lecture 2 - Floating Point Representation"),

    # Module - I/O Interfacing, Interrupts & DMA
    (r"Memory Mapped I/O|Isolated I/O", "Module - I/O Interfacing, Interrupts & DMA/Lecture 1 - I/O Interface, Memory Mapped I/O, Isolated I/O"),
    (r"Programmed I/O|Interrupt Driven", "Module - I/O Interfacing, Interrupts & DMA/Lecture 2 - Programmed I/O & Interrupt Driven I/O"),
    (r"Interrupts & Interrupt Processing|Multiple Interrupts", "Module - I/O Interfacing, Interrupts & DMA/Lecture 3 - Interrupts & Interrupt Processing"),
    (r"DMA ALL GATE|DMA", "Module - I/O Interfacing, Interrupts & DMA/Lecture 4 - DMA - Direct Memory Access"),

    # Pipeline
    (r"Pipeline|Pipelining", "Module - Pipeline/Pipeline Lectures"),

    # (OPTIONAL) (OLD) Module: Cache Memory
    (r"OLD.*Cache|\(OLD\)", "(OPTIONAL) (OLD) Module: Cache Memory/Old Cache Lectures"),

    # Module 3 - Cache Memory
    (r"Direct Mapped Cache", "Module 3 - Cache Memory/Lecture 2 - Direct Mapped Cache"),
    (r"Set Associative Cache|Set Associative", "Module 3 - Cache Memory/Lecture 3 - Set Associative Cache"),
    (r"Fully Associative Cache|Fully Associative", "Module 3 - Cache Memory/Lecture 4 - Fully Associative Cache"),
    (r"Replacement Policies|Misses", "Module 3 - Cache Memory/Lecture 5 - Replacement Policies & Types of Misses"),
    (r"AMAT|Average Memory Access Time", "Module 3 - Cache Memory/Lecture 6 - Average Memory Access Time AMAT"),
    (r"Cache Write Policies|Write Back", "Module 3 - Cache Memory/Lecture 7 - Cache Write Policies"),
    (r"Cache Memory|Locality|Cache", "Module 3 - Cache Memory/Lecture 1 - Cache Memory, Locality"),

    # Module 2 - The CPU
    (r"Registers & Status Flags|Registers", "Module 2 - The CPU/Lecture 1 - Registers & Status Flags"),
    (r"RISC & CISC|ISA", "Module 2 - The CPU/Lecture 2 - ISA, RISC & CISC Architecture"),
    (r"Instruction Format|Expanding Opcode|Opcode", "Module 2 - The CPU/Lecture 3 - Instruction Format & Expanding Opcode"),
    (r"Branch Instructions|ALU Operations|Machine Instructions", "Module 2 - The CPU/Lecture 4 - Instruction Types, ALU & Branching"),
    (r"Instruction Execution Cycle", "Module 2 - The CPU/Lecture 5 - Instruction Execution Cycle"),
    (r"Addressing Modes", "Module 2 - The CPU/Lecture 6 - Addressing Modes"),

    # Module 1 - Basic Components & Main Memory
    (r"Addressability|Endianness|Byte Ordering|Main Memory", "Module 1 - Basic Components of Computer & Main Memory/Lecture 2A - Main Memory - Addressability"),
    (r"System Bus|Memory Interfacing|Interleaving", "Module 1 - Basic Components of Computer & Main Memory/Lecture 3A - System Bus"),
    (r"Architecture Vs Organization|Stored Program|IO Devices|RAM Vs ROM|COA|Overview of COA", "Module 1 - Basic Components of Computer & Main Memory/Lecture 1"),

    # Algorithms topics (if existing files are named algorithm-specific)
    (r"BFS|DFS|Breadth First|Depth First", "Module 1 - Basic Components of Computer & Main Memory/Lecture 1"),
    (r"Divide and Conquer", "Module 2 - The CPU/Lecture 2 - ISA, RISC & CISC Architecture"),
    (r"Dynamic Programming|Knapsack|LCS|Matrix Chain", "Module 3 - Cache Memory/Lecture 1 - Cache Memory, Locality"),
    (r"Greedy|Huffman|Interval Scheduling|Spanning Tree|Dijkstra|Shortest Paths", "Module 3 - Cache Memory/Lecture 5 - Replacement Policies & Types of Misses"),
    (r"Sorting|Merge Sort|Quick Sort", "Module 2 - The CPU/Lecture 3 - Instruction Format & Expanding Opcode"),
    (r"Time Complexity|Recurrence|Master", "Module 1 - Basic Components of Computer & Main Memory/Lecture 1"),
    (r"Maximum and Minimum|Tournament Method", "Module 2 - The CPU/Lecture 1 - Registers & Status Flags")
]

def organize_files():
    files = [f for f in os.listdir(BASE_DIR) if os.path.isfile(os.path.join(BASE_DIR, f))]
    print(f"Total files to inspect: {len(files)}")

    moved_count = 0
    skipped_count = 0

    for filename in files:
        if filename.endswith(".crdownload") or filename.endswith(".tmp") or filename.endswith(".part"):
            print(f"Skipping downloading file: {filename}")
            skipped_count += 1
            continue

        target_subfolder = None
        for pattern, folder in RULES:
            if re.search(pattern, filename, re.IGNORECASE):
                target_subfolder = folder
                break

        if target_subfolder:
            dest_dir = os.path.join(BASE_DIR, target_subfolder)
            os.makedirs(dest_dir, exist_ok=True)
            src_path = os.path.join(BASE_DIR, filename)
            dest_path = os.path.join(dest_dir, filename)
            shutil.move(src_path, dest_path)
            print(f"Moved: '{filename}' -> '{target_subfolder}/'")
            moved_count += 1
        else:
            print(f"No match for: '{filename}' (kept in root)")

    print(f"\nFinished organizing: {moved_count} files moved, {skipped_count} temp files skipped.")

if __name__ == '__main__':
    organize_files()
