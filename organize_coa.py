import os
import sys

# The COA module structure provided by the user
COA_STRUCTURE = [
    ("Module 1 - Basic Components of Computer & Main Memory", [
        "Lecture 1",
        "Lecture 2A - Main Memory - Addressability",
        "Lecture 2B - Byte Ordering - Endianness",
        "Lecture 2C - Practice Questions - Endianness",
        "Lecture 3A - System Bus",
        "Lecture 3B - Memory Interfacing & Expansion",
        "Lecture 3C - GATE Questions - Memory Interleaving",
    ]),
    ("Module 2 - The CPU", [
        "Lecture 1 - Registers & Status Flags",
        "Lecture 2 - ISA, RISC & CISC Architecture",
        "Lecture 3 - Instruction Format & Expanding Opcode",
        "Lecture 4 - Instruction Types, ALU & Branching",
        "Lecture 5 - Instruction Execution Cycle",
        "Lecture 6 - Addressing Modes",
    ]),
    ("Module 3 - Cache Memory", [
        "Lecture 1 - Cache Memory, Locality",
        "Lecture 2 - Direct Mapped Cache",
        "Lecture 3 - Set Associative Cache",
        "Lecture 4 - Fully Associative Cache",
        "Lecture 5 - Replacement Policies & Types of Misses",
        "Lecture 6 - Average Memory Access Time AMAT",
        "Lecture 7 - Cache Write Policies",
    ]),
    ("(OPTIONAL) (OLD) Module: Cache Memory", [
        "Old Cache Lectures",
    ]),
    ("Module - Pipeline", [
        "Pipeline Lectures",
    ]),
    ("Module - I/O Interfacing, Interrupts & DMA", [
        "Lecture 1 - I/O Interface, Memory Mapped I/O, Isolated I/O",
        "Lecture 2 - Programmed I/O & Interrupt Driven I/O",
        "Lecture 3 - Interrupts & Interrupt Processing",
        "Lecture 4 - DMA - Direct Memory Access",
        "Lecture 5 - DMA ALL GATE PYQs & Practice",
    ]),
    ("Module: Floating Point Representation", [
        "Lecture 1 - Fixed Point Representation",
        "Lecture 2 - Floating Point Representation",
        "Lecture 3 - Floating Point Special Forms & GATE PYQs",
    ]),
    ("Students' Hand Written Notes", [
        "Handwritten Notes",
    ])
]

def create_folders(base_path):
    print(f"Creating module folders in: {base_path}")
    for mod_title, subfolders in COA_STRUCTURE:
        mod_dir = os.path.join(base_path, mod_title)
        os.makedirs(mod_dir, exist_ok=True)
        print(f"Created: {mod_dir}")
        for sub in subfolders:
            sub_dir = os.path.join(mod_dir, sub)
            os.makedirs(sub_dir, exist_ok=True)
            print(f"  Created: {sub_dir}")

if __name__ == '__main__':
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/skc/Downloads/algorithms"
    create_folders(base_dir)
