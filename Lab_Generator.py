from ortools.sat.python import cp_model
import pandas as pd
import random
import os
import datetime

# Define class duration constants
LAB_CLASS_DURATION = 2.0     # 2 hours duration
START_TIME = "8:15"          # Start time of the day

class LabTimetableGenerator:
    """
    Lab-only timetable generator for multiple classes across different years.
    Each class has multiple batches for lab sessions.
    Optimized for minimal student idle gaps and teacher timing constraints.
    """
    
    def __init__(self, department_data):
        """
        Initialize the lab timetable generator with department data.
        
        Args:
            department_data: Dictionary containing department resources and configuration
                including years, classes per year, subjects, teachers, lab_rooms, etc.
        """
        # Define time slots and breaks
        self.morning_break = "10:15-10:30"  # 15-minute morning break
        self.lunch_break = "12:30-1:15"     # 45-minute lunch break
        self.evening_break = "3:15-3:30"    # 15-minute evening break
        self.morning_slots = ["8:15-9:15", "9:15-10:15"]
        self.midday_slots = ["10:30-11:30", "11:30-12:30"]
        self.afternoon_slots = ["1:15-2:15", "2:15-3:15"]
        self.evening_slots = ["3:30-4:30", "4:30-5:30"]
        self.all_time_slots = (
            self.morning_slots + [self.morning_break] +
            self.midday_slots + [self.lunch_break] +
            self.afternoon_slots + [self.evening_break] +
            self.evening_slots
        )
        self.break_slots = [self.morning_break, self.lunch_break, self.evening_break]
        
        # Extract data from input
        self.years = department_data["years"]
        self.classes_per_year = department_data["classes_per_year"]
        self.all_classes = []
        
        # Generate all class names (e.g., SE1, SE2, TE1, TE2, etc.)
        for year in self.years:
            if year == "Second Year":
                year_prefix = "SE"
            elif year == "Third Year":
                year_prefix = "TE"
            elif year == "Fourth Year":
                year_prefix = "BE"
            else:
                year_prefix = year[:2].upper()
                
            for i in range(1, self.classes_per_year + 1):
                self.all_classes.append(f"{year_prefix}{i}")
        
        # Extract other department data
        self.teachers = department_data["teachers"]
        self.lab_rooms = department_data["lab_rooms"]
        self.subjects_by_year = department_data["subjects_by_year"]
        self.course_structure = department_data["course_structure"]
        self.lab_teacher_assignments = department_data["lab_teacher_assignments"]
        
        # Define days of the week
        self.days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        
        # Assign teacher availability
        self.teacher_availability = department_data["teacher_availability"]
        
        # Slots available for scheduling
        self.available_slots = [slot for slot in self.all_time_slots if slot not in self.break_slots]
        
        # Create consecutive slots mapping for 2-hour lab sessions
        self.consecutive_slots = {}
        all_teaching_slots = self.morning_slots + self.midday_slots + self.afternoon_slots + self.evening_slots
        for i in range(len(all_teaching_slots) - 1):
            # Only consecutive if no break in between
            if (
                (all_teaching_slots[i] in self.morning_slots and all_teaching_slots[i+1] in self.morning_slots) or
                (all_teaching_slots[i] in self.midday_slots and all_teaching_slots[i+1] in self.midday_slots) or
                (all_teaching_slots[i] in self.afternoon_slots and all_teaching_slots[i+1] in self.afternoon_slots) or
                (all_teaching_slots[i] in self.evening_slots and all_teaching_slots[i+1] in self.evening_slots)
            ):
                self.consecutive_slots[all_teaching_slots[i]] = all_teaching_slots[i+1]
        
        # Special case: 10:30-11:30 and 11:30-12:30 can be used for a lab
        self.consecutive_slots["10:30-11:30"] = "11:30-12:30"
        
        # Generate batch names for each class
        NUM_BATCHES_PER_CLASS = 4  # Fixed number of batches per class
        self.batches_by_class = {}
        for class_name in self.all_classes:
            year_prefix = class_name[:2].upper()  # SE, TE, BE
            class_number = class_name[2]          # 1, 2, 3, etc.
            self.batches_by_class[class_name] = [f"{year_prefix}{class_number}{batch}" for batch in range(1, NUM_BATCHES_PER_CLASS + 1)]
        
        # Initialize model and variables
        self.model = cp_model.CpModel()
        self.assignments = {}
        self.class_timetables = {}
        self.teacher_timetables = {}
        
        # Define allowed lab slots for each year
        self.te_lab_slots = ["8:15-9:15", "9:15-10:15", "10:30-11:30", "11:30-12:30", "1:15-2:15", "2:15-3:15"]
        self.se_lab_slots = ["10:30-11:30", "11:30-12:30", "1:15-2:15", "2:15-3:15", "3:30-4:30", "4:30-5:30"]
        # Special slots for specific subjects
        self.ajp_lab_slots = ["3:30-4:30", "4:30-5:30"]  # AJP labs in 3:30-5:30
        self.te_cluster_slots = ["8:15-9:15", "9:15-10:15"]  # TE labs clustering (except AJP)
        self.se_cluster_slots = ["10:30-11:30", "11:30-12:30"]  # SE labs clustering
    
    def _get_year_from_class(self, class_name):
        """
        Gets the year (Second Year, Third Year, etc.) from class name (SE1, TE2, etc.).
        """
        prefix = class_name[:2].upper()
        if prefix == "SE":
            return "Second Year"
        elif prefix == "TE":
            return "Third Year"
        elif prefix == "BE":
            return "Fourth Year"
        else:
            print(f"Warning: Unknown prefix '{prefix}' in class name '{class_name}'. Defaulting to Second Year.")
            return "Second Year"
    
    def create_lab_variables(self):
        """
        Creates decision variables for lab sessions only.
        """
        print("Creating lab variables...")
        variable_count = 0
        
        for class_name in self.all_classes:
            year = self._get_year_from_class(class_name)
            subjects = self.subjects_by_year[year]
            
            for subject in subjects:
                if subject in self.course_structure and self.course_structure[subject].get("labs", 0) > 0:
                    for day in self.days:
                        # Choose allowed slots based on subject and year
                        if subject == "AJP":
                            allowed_slots = self.ajp_lab_slots
                        elif year == "Third Year":
                            allowed_slots = self.te_cluster_slots
                        elif year == "Second Year":
                            allowed_slots = self.se_cluster_slots
                        else:
                            allowed_slots = self.available_slots
                        
                        for time_slot in allowed_slots:
                            if time_slot not in self.consecutive_slots:
                                continue  # Skip slots that can't start a 2-hour lab
                            
                            for batch in self.batches_by_class[class_name]:
                                teacher = self.lab_teacher_assignments[year][subject]
                                for lab in self.lab_rooms:
                                    var_name = f"{class_name}{subject}_Lab{batch}{day}{time_slot}{teacher}{lab}"
                                    key = (class_name, subject, "lab", batch, day, time_slot, teacher, lab)
                                    self.assignments[key] = self.model.NewBoolVar(var_name)
                                    variable_count += 1
        
        print(f"Created {variable_count} lab variables")
    
    def add_lab_constraints(self):
        """
        Adds constraints for lab scheduling.
        """
        print("Adding lab constraints...")
        
        # Each lab batch must have required number of lab sessions
        for class_name in self.all_classes:
            year = self._get_year_from_class(class_name)
            subjects = self.subjects_by_year[year]
            
            for subject in subjects:
                if subject in self.course_structure and self.course_structure[subject].get("labs", 0) > 0:
                    for batch in self.batches_by_class[class_name]:
                        lab_vars = []
                        for day in self.days:
                            # Choose allowed slots based on subject and year
                            if subject == "AJP":
                                allowed_slots = self.ajp_lab_slots
                            elif year == "Third Year":
                                allowed_slots = self.te_cluster_slots
                            elif year == "Second Year":
                                allowed_slots = self.se_cluster_slots
                            else:
                                allowed_slots = self.available_slots
                            
                            for time_slot in allowed_slots:
                                if time_slot in self.consecutive_slots:
                                    teacher = self.lab_teacher_assignments[year][subject]
                                    for lab in self.lab_rooms:
                                        # Enforce lab room constraints
                                        if subject in ["ADE", "DC"] and lab != "501":
                                            continue
                                        if subject == "MNA" and lab != "504":
                                            continue
                                        key = (class_name, subject, "lab", batch, day, time_slot, teacher, lab)
                                        if key in self.assignments:
                                            lab_vars.append(self.assignments[key])
                                            # HARD CONSTRAINT: If a lab starts at this slot, it must continue in the next slot
                                            next_slot = self.consecutive_slots[time_slot]
                                            next_key = (class_name, subject, "lab", batch, day, next_slot, teacher, lab)
                                            if next_key in self.assignments:
                                                self.model.AddImplication(self.assignments[key], self.assignments[next_key])
                        
                        if lab_vars:
                            self.model.Add(sum(lab_vars) == self.course_structure[subject]["labs"])
        
        # Teacher availability constraints
        for teacher in self.teachers:
            for day in self.days:
                for time_slot in self.available_slots:
                    if time_slot in self.consecutive_slots:
                        teacher_vars = []
                        for key, var in self.assignments.items():
                            class_name, subject, activity_type, batch, day_key, time_slot_key, teacher_key, lab = key
                            if day_key == day and time_slot_key == time_slot and teacher_key == teacher:
                                teacher_vars.append(var)
                        
                        if teacher_vars:
                            # Check teacher availability
                            if teacher in self.teacher_availability and day in self.teacher_availability[teacher]:
                                if time_slot not in self.teacher_availability[teacher][day]:
                                    # Teacher not available at this time
                                    self.model.Add(sum(teacher_vars) == 0)
                            # Teacher can only teach one lab at a time
                            self.model.Add(sum(teacher_vars) <= 1)
        
        # Lab room availability constraints - only one lab per room at any time
        for lab in self.lab_rooms:
            for day in self.days:
                for time_slot in self.available_slots:
                    if time_slot in self.consecutive_slots:
                        lab_vars = []
                        for key, var in self.assignments.items():
                            class_name, subject, activity_type, batch, day_key, time_slot_key, teacher, lab_key = key
                            if day_key == day and time_slot_key == time_slot and lab_key == lab:
                                lab_vars.append(var)
                        
                        if lab_vars:
                            # Only one lab per room at any time (HARD CONSTRAINT)
                            self.model.Add(sum(lab_vars) <= 1)
        
        # Batch availability constraints (no batch can have multiple labs at the same time)
        for class_name in self.all_classes:
            for batch in self.batches_by_class[class_name]:
                for day in self.days:
                    for time_slot in self.available_slots:
                        if time_slot in self.consecutive_slots:
                            batch_vars = []
                            for key, var in self.assignments.items():
                                class_name_key, subject, activity_type, batch_key, day_key, time_slot_key, teacher, lab = key
                                if class_name_key == class_name and batch_key == batch and day_key == day and time_slot_key == time_slot:
                                    batch_vars.append(var)
                            
                            if batch_vars:
                                # A batch can only have one lab at a time
                                self.model.Add(sum(batch_vars) <= 1)
        
        # Ensure better room utilization - when multiple labs are scheduled, use different rooms
        for day in self.days:
            for time_slot in self.available_slots:
                if time_slot in self.consecutive_slots:
                    # Count how many labs are scheduled at this time slot
                    total_labs_at_time = []
                    for key, var in self.assignments.items():
                        class_name, subject, activity_type, batch, day_key, time_slot_key, teacher, lab = key
                        if day_key == day and time_slot_key == time_slot:
                            total_labs_at_time.append(var)
                    
                    if total_labs_at_time:
                        # If we have multiple labs at the same time, ensure they use different rooms
                        # This is handled by the room availability constraint above
                        # But we can add a soft constraint to prefer using more rooms
                        pass
    
    def add_optimization_objective(self):
        """
        Adds optimization objectives to minimize idle gaps and optimize lab scheduling.
        """
        print("Adding optimization objectives...")
        
        gap_vars = []
        slot_index = {slot: idx for idx, slot in enumerate(self.available_slots)}
        num_slots = len(self.available_slots)
        for class_name in self.all_classes:
            for batch in self.batches_by_class[class_name]:
                for day in self.days:
                    # Always build slot_vars to match self.available_slots length
                    slot_vars = []
                    for slot in self.available_slots:
                        if slot in self.consecutive_slots:
                            found = False
                            for key, var in self.assignments.items():
                                if (key[0] == class_name and key[2] == "lab" and 
                                    key[3] == batch and key[4] == day and key[5] == slot):
                                    slot_vars.append(var)
                                    found = True
                                    break
                            if not found:
                                slot_vars.append(None)
                        else:
                            slot_vars.append(None)
                    # Only check for gaps where i-1, i, i+1 are all valid indices
                    for i in range(1, num_slots-1):
                        prev_var = slot_vars[i-1]
                        curr_var = slot_vars[i]
                        next_var = slot_vars[i+1]
                        if curr_var is not None and prev_var is not None and next_var is not None:
                            gap = self.model.NewBoolVar(f"gap_{class_name}_{batch}_{day}_{i}")
                            self.model.AddBoolAnd([prev_var, next_var, curr_var.Not()]).OnlyEnforceIf(gap)
                            self.model.AddBoolOr([prev_var.Not(), next_var.Not(), curr_var]).OnlyEnforceIf(gap.Not())
                            gap_vars.append(gap)
        
        # Minimize late sessions (prefer earlier slots)
        late_session_vars = []
        for class_name in self.all_classes:
            for batch in self.batches_by_class[class_name]:
                for day in self.days:
                    for i, slot in enumerate(self.available_slots):
                        if slot in self.consecutive_slots:
                            for key, var in self.assignments.items():
                                if (key[0] == class_name and key[2] == "lab" and 
                                    key[3] == batch and key[4] == day and key[5] == slot):
                                    weight = i * 2
                                    for _ in range(weight):
                                        late_session_vars.append(var)
        
        # Minimize lab room usage (prefer fewer rooms)
        used_lab_vars = []
        for lab in self.lab_rooms:
            used = self.model.NewBoolVar(f"used_lab_{lab}")
            lab_vars = [var for key, var in self.assignments.items() if key[7] == lab]
            if lab_vars:
                self.model.AddBoolOr(lab_vars).OnlyEnforceIf(used)
                self.model.AddBoolAnd([var.Not() for var in lab_vars]).OnlyEnforceIf(used.Not())
                used_lab_vars.append(used)
        
        # Penalize room conflicts more heavily
        room_conflict_vars = []
        for lab in self.lab_rooms:
            for day in self.days:
                for time_slot in self.available_slots:
                    if time_slot in self.consecutive_slots:
                        lab_vars = [var for key, var in self.assignments.items() 
                                   if key[7] == lab and key[4] == day and key[5] == time_slot]
                        if len(lab_vars) > 1:
                            # This should not happen with our constraints, but add penalty just in case
                            conflict = self.model.NewBoolVar(f"room_conflict_{lab}_{day}_{time_slot}")
                            self.model.Add(sum(lab_vars) <= 1).OnlyEnforceIf(conflict.Not())
                            self.model.Add(sum(lab_vars) >= 2).OnlyEnforceIf(conflict)
                            room_conflict_vars.append(conflict)
        
        # Combined objective: minimize gaps, late sessions, and maximize lab room usage
        self.model.Minimize(
            10 * sum(gap_vars) +      # High penalty for gaps
            2 * sum(late_session_vars) +  # Medium penalty for late sessions
            -5 * sum(used_lab_vars) +     # Reward for using more lab rooms
            100 * sum(room_conflict_vars)  # Very high penalty for room conflicts
        )
    
    def generate_teacher_timetables(self):
        """
        Generates individual teacher timetables from the lab schedules.
        """
        print("Generating teacher timetables...")
        
        # Initialize teacher timetables
        for teacher in self.teachers:
            self.teacher_timetables[teacher] = {}
            for day in self.days:
                self.teacher_timetables[teacher][day] = {}
                for time_slot in self.all_time_slots:
                    self.teacher_timetables[teacher][day][time_slot] = None
        
        # Extract teacher assignments from class timetables
        for class_name in self.all_classes:
            for day in self.days:
                for time_slot in self.available_slots:
                    if time_slot in self.consecutive_slots:
                        for batch, lab in self.class_timetables[class_name]["labs"][day].get(time_slot, {}).items():
                            if lab and isinstance(lab, dict) and lab.get("teacher") and not lab.get("continued", False):
                                teacher = lab["teacher"]
                                if teacher in self.teacher_timetables:
                                    self.teacher_timetables[teacher][day][time_slot] = {
                                        "type": "Lab",
                                        "subject": lab.get("subject", ""),
                                        "class": class_name,
                                        "batch": batch,
                                        "lab": lab.get("lab", "")
                                    }
        
        print(f"Generated timetables for {len(self.teacher_timetables)} teachers")
    
    def solve(self, timeout_seconds=120):
        """
        Solves the CP-SAT model and extracts the timetable.
        """
        print("Creating variables and constraints...")
        self.create_lab_variables()
        self.add_lab_constraints()
        self.add_optimization_objective()
        
        print("Solving model with optimized parameters...")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        solver.parameters.num_search_workers = 16
        solver.parameters.log_search_progress = True
        
        status = solver.Solve(self.model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"Solution found with status: {status}")
            print(f"Objective value: {solver.ObjectiveValue()}")
            print(f"Best bound: {solver.BestObjectiveBound()}")
            print(f"Gap: {solver.ResponseProto().gap_integral:.2f}")
            self._extract_timetables(solver)
            return True
        else:
            print(f"No solution found. Status: {status}")
            return False
    
    def _extract_timetables(self, solver):
        """
        Extracts the timetable from the solver solution.
        """
        # Initialize timetables for each class
        for class_name in self.all_classes:
            self.class_timetables[class_name] = {"labs": {}}
            for day in self.days:
                self.class_timetables[class_name]["labs"][day] = {}
                for time_slot in self.all_time_slots:
                    self.class_timetables[class_name]["labs"][day][time_slot] = {}
                    if time_slot in self.break_slots:
                        if time_slot == self.lunch_break:
                            self.class_timetables[class_name]["labs"][day][time_slot] = {"subject": "LUNCH BREAK"}
                        elif time_slot == self.morning_break:
                            self.class_timetables[class_name]["labs"][day][time_slot] = {"subject": "MORNING BREAK"}
                        elif time_slot == self.evening_break:
                            self.class_timetables[class_name]["labs"][day][time_slot] = {"subject": "EVENING BREAK"}
                
                for time_slot in self.available_slots:
                    for batch in self.batches_by_class[class_name]:
                        self.class_timetables[class_name]["labs"][day][time_slot][batch] = None
        
        # Extract lab assignments
        for key, var in self.assignments.items():
            if solver.BooleanValue(var):
                class_name, subject, activity_type, batch, day, time_slot, teacher, lab = key
                self.class_timetables[class_name]["labs"][day][time_slot][batch] = {
                    "subject": subject,
                    "teacher": teacher,
                    "lab": lab
                }
                
                # Add lab assignment for the second hour (consecutive slot)
                if time_slot in self.consecutive_slots:
                    next_slot = self.consecutive_slots[time_slot]
                    if next_slot in self.available_slots:
                        self.class_timetables[class_name]["labs"][day][next_slot][batch] = {
                            "subject": subject,
                            "teacher": teacher,
                            "lab": lab,
                            "continued": True
                        }
    
    def print_timetable_for_class(self, class_name):
        """
        Prints the lab timetable for a specific class.
        """
        if class_name not in self.class_timetables:
            print(f"No timetable available for class: {class_name}")
            return
        
        timetable = self.class_timetables[class_name]
        
        print(f"\n{'='*120}")
        print(f"LAB TIMETABLE FOR {class_name} - {self._get_year_from_class(class_name)}")
        print(f"{'='*120}")
        
        # Print timetable header
        time_header = "Time Slot"
        header = f"{time_header:<15} | "
        for day in self.days:
            header += f"{day:<20} | "
        print(header)
        print("-" * 120)
        
        for time_slot in self.all_time_slots:
            row = f"{time_slot:<15} | "
            for day in self.days:
                # Check if it's a break slot
                if time_slot in self.break_slots:
                    if time_slot == self.lunch_break:
                        row += f"{'LUNCH BREAK':<20} | "
                    elif time_slot == self.morning_break:
                        row += f"{'MORNING BREAK':<20} | "
                    elif time_slot == self.evening_break:
                        row += f"{'EVENING BREAK':<20} | "
                    continue
                
                # Get labs for this slot
                labs = []
                for batch, lab in timetable["labs"][day].get(time_slot, {}).items():
                    if lab and not lab.get("continued", False):
                        labs.append(f"{lab['subject']} ({lab['teacher']}) {batch} {lab['lab']}")
                    elif lab and lab.get("continued", False):
                        # Show continued labs in the second hour
                        labs.append(f"{lab['subject']} ({lab['teacher']}) {batch} {lab['lab']} (cont.)")
                
                if labs:
                    cell = " && ".join(labs)
                    if len(cell) > 18:
                        cell = cell[:17] + "…"
                    row += f"{cell:<20} | "
                else:
                    row += f"{'---':<20} | "
            
            print(row)
        
        # Print detailed lab information
        print(f"\nDETAILED LAB SCHEDULE FOR {class_name}:")
        print("-" * 120)
        for day in self.days:
            labs_for_day = False
            for time_slot in self.available_slots:
                if time_slot in self.consecutive_slots:
                    labs_in_slot = False
                    for batch, lab in timetable["labs"][day].get(time_slot, {}).items():
                        if lab and not lab.get("continued", False):
                            if not labs_for_day:
                                print(f"\n{day}:")
                                labs_for_day = True
                            if not labs_in_slot:
                                print(f"  {time_slot} - {self.consecutive_slots[time_slot]}:")
                                labs_in_slot = True
                            print(f"    {batch}: {lab['subject']} in {lab['lab']} with {lab['teacher']}")
                    # Also show continued labs in the second hour
                    next_slot = self.consecutive_slots[time_slot]
                    if next_slot in self.available_slots:
                        for batch, lab in timetable["labs"][day].get(next_slot, {}).items():
                            if lab and lab.get("continued", False):
                                if not labs_for_day:
                                    print(f"\n{day}:")
                                    labs_for_day = True
                                if not labs_in_slot:
                                    print(f"  {next_slot}:")
                                    labs_in_slot = True
                                print(f"    {batch}: {lab['subject']} in {lab['lab']} with {lab['teacher']} (continued)")

def main():
    """
    Main function to run the lab-only timetable generator.
    """
    # Use only SE1 and TE1
    years = ["Second Year", "Third Year"]
    classes_per_year = 1
    
    # Subjects with labs only
    subjects_by_year = {
        "Second Year": ["ADE", "OS", "SDA", "PDS"],  # Only subjects with labs
        "Third Year": ["DBMS", "AJP", "DC", "MNA", "DAUPL"]   # Only subjects with labs
    }
    
    # Lab teacher assignments - using the same teachers as lectures for consistency
    lab_teacher_assignments = {
        "Third Year": {
            "DBMS": "Patil",
            "AJP": "Yadav",
            "DC": "Chimmana",
            "MNA": "Dolli",
            "DAUPL": "Nahatkar"
        },
        "Second Year": {
            "ADE": "Dolli",
            "OS": "Chimmana",
            "SDA": "Nahatkar",
            "PDS": "Patil",
            "CEP": "Yadav",
            "PDCR": "Vidhate"
        }
    }
    
    # Build flat set of all unique teacher names
    all_teachers = set()
    for year_map in lab_teacher_assignments.values():
        for teacher in year_map.values():
            all_teachers.add(teacher)
    all_teachers = list(all_teachers)
    
    lab_rooms = [str(501 + i) for i in range(5)]
    course_structure = {}
    for year, year_subjects in subjects_by_year.items():
        for subject in year_subjects:
            course_structure[subject] = {
                "labs": 1,  # Each subject has 1 lab session
                "lab_duration": LAB_CLASS_DURATION
            }
    
    # Define allowed slots for Yadav and Vidhate
    allowed_slots_yadav_vidhate = [
        "10:30-11:30", "11:30-12:30", "1:15-2:15", "2:15-3:15", "3:30-4:30", "4:30-5:30"
    ]
    
    teacher_availability = {}
    for teacher in all_teachers:
        teacher_availability[teacher] = {day: [] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}
    
    # Restrict Moon, Chimmana, Nahatkar, Patil, Dolli to 8:15-3:15 slots only
    for teacher in ["Moon", "Chimmana", "Nahatkar", "Patil", "Dolli"]:
        if teacher in teacher_availability:
            for day in teacher_availability[teacher]:
                teacher_availability[teacher][day] = [
                    "8:15-9:15", "9:15-10:15", "10:30-11:30", "11:30-12:30", 
                    "1:15-2:15", "2:15-3:15"
                ]
    
    # Restrict Yadav and Vidhate to 10:30-5:30 slots only
    for teacher in ["Yadav", "Vidhate"]:
        if teacher in teacher_availability:
            for day in teacher_availability[teacher]:
                teacher_availability[teacher][day] = [
                    "10:30-11:30", "11:30-12:30", "1:15-2:15", "2:15-3:15", 
                    "3:30-4:30", "4:30-5:30"
                ]
    
    department_data = {
        "years": years,
        "classes_per_year": classes_per_year,
        "teachers": all_teachers,
        "lab_rooms": lab_rooms,
        "subjects_by_year": subjects_by_year,
        "course_structure": course_structure,
        "lab_teacher_assignments": lab_teacher_assignments,
        "teacher_availability": teacher_availability
    }
    
    print("\nGenerating LAB-ONLY timetables for the following configuration:")
    print(f"Years: {', '.join(years)}")
    print(f"Classes per year: {classes_per_year}")
    for year in years:
        print(f"\n{year} Lab Subjects: {', '.join(subjects_by_year[year])}")
        print(f"{year} Lab Teachers:")
        for subject, teacher in lab_teacher_assignments[year].items():
            print(f"  - {subject}: {teacher}")
    print(f"\nLab Rooms: {', '.join(lab_rooms)}")
    print("=" * 50)
    print("\nLab Duration: 2.0 hours")
    print(f"Start time: {START_TIME} AM")
    print("\nTime Slots:")
    print("Morning: " + ", ".join(["8:15-9:15", "9:15-10:15"]))
    print("Break: 10:15-10:30")
    print("Midday: " + ", ".join(["10:30-11:30", "11:30-12:30"]))
    print("Lunch: 12:30-1:15")
    print("Afternoon: " + ", ".join(["1:15-2:15", "2:15-3:15"]))
    print("Break: 3:15-3:30")
    print("Evening: " + ", ".join(["3:30-4:30", "4:30-5:30"]))
    print("=" * 50)
    
    generator = LabTimetableGenerator(department_data)
    
    if generator.solve():
        for class_name in generator.all_classes:
            generator.print_timetable_for_class(class_name)
        return generator
    else:
        print("No feasible lab timetable found.")
        return None

if __name__ == "__main__":
    main()
