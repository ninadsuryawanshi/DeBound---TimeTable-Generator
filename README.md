# DeBound---TimeTable-Generator

## Overview

DeBound---TimeTable-Generator is an automated academic timetabling system designed to generate conflict-free schedules for laboratories and lectures. Powered by Google's [OR-Tools](https://developers.google.com/optimization/), specifically the CP-SAT solver, this project efficiently handles complex constraints commonly found in educational environments. The system produces professional, color-coded Excel timetables suitable for direct use or further refinement.

## What It Does

- **Automated Timetabling:** Generates optimal lab and lecture schedules without conflicts.
- **Constraint Handling:** Supports a wide range of constraints including room availability, instructor assignments, and student groups.
- **Two-Phase Generation:** Uses separate modules for labs and lectures to maximize flexibility:
  - `Lab_Generator.py` for laboratory schedules
  - `Lecture_Generator.py` for lecture schedules
- **Professional Output:** Exports schedules to Excel with color-coding for easy interpretation.

## How It Works

1. **Constraint Programming:** Utilizes OR-Tools CP-SAT solver, modeling the scheduling problem as a set of variables and constraints (as shown in the attached output image).
2. **Variable Creation:** Defines variables for time slots, rooms, instructors, and student groups.
3. **Constraint Addition:** Implements constraints such as "no instructor double booking," "room capacity," and "student group exclusivity."
4. **Optimization:** Solves the model to find a solution that satisfies all constraints and optimizes criteria (e.g., minimizing back-to-back sessions).
5. **Excel Export:** The solution is written to a color-coded Excel file, allowing users to visualize and distribute the schedule.

## Example Output

- Output Excel files (found in the repository) display the finalized timetable in a user-friendly format.

## How to Use

### Prerequisites

- Python 3.x
- [Google OR-Tools](https://pypi.org/project/ortools/)
- `pandas` and `openpyxl` (for Excel export)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ninadsuryawanshi/DeBound---TimeTable-Generator.git
   cd DeBound---TimeTable-Generator
   ```
2. Install dependencies:
   ```bash
   pip install ortools pandas openpyxl
   ```

### Running the Generator

1. Prepare your input data (classes, rooms, instructors, student groups) as specified in the documentation or example files.
2. Run the lab or lecture generator:
   ```bash
   python Lab_Generator.py
   python Lecture_Generator.py
   ```
3. Review the solver output in the console (`image1`) and check the generated Excel timetable.

### Accessing the Output

- The generated timetable will be saved as an Excel file in the repository directory.
- Open the Excel file to view the color-coded schedule for all classes.

## Public Use

DeBound---TimeTable-Generator is open source and available for anyone to use or modify. Schools, universities, and training centers can adapt the system to their specific scheduling requirements. Contributions and suggestions are welcome!



For questions or contributions, please open an issue or pull request in the repository.
