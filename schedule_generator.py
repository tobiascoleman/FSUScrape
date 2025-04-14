import sqlite3
import itertools

def generate_optimal_schedules(required_courses, optional_courses, earliest_time, latest_time, 
                              preferred_days, max_courses, year, term, prioritize_gaps, username):
    """
    Generate optimal course schedules based on constraints.
    
    Args:
        required_courses (list): Course codes that must be included
        optional_courses (list): Course codes that should be included if possible
        earliest_time (str): Earliest time for classes (e.g., '0800')
        latest_time (str): Latest time for classes (e.g., '1700')
        preferred_days (str): String of preferred days (e.g., 'MWF')
        max_courses (int): Maximum number of courses to include
        year (str): Year for the courses (e.g., '2025')
        term (str): Term for the courses (e.g., 'Fall')
        prioritize_gaps (bool): Whether to minimize gaps between classes
        username (str): Username of the current user
        
    Returns:
        list: List of possible schedules, each containing course information
    """
    conn = sqlite3.connect('fsu_courses.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Convert time constraints to integers for proper comparison
    earliest_time_int = int(earliest_time)
    latest_time_int = int(latest_time)
    
    print(f"Finding courses between {earliest_time} ({earliest_time_int}) and {latest_time} ({latest_time_int})")
    
    # Remove duplicates and get all candidate courses
    all_courses = list(set(required_courses + optional_courses))
    
    # Get all sections of the candidate courses that meet time and day constraints
    course_sections = {}
    for course_code in all_courses:
        # First, get all sections of this course
        cursor.execute("""
            SELECT c.*, 
                   GROUP_CONCAT(i.instructorName) as instructors
            FROM courses c
            LEFT JOIN course_instructors ci ON c.id = ci.course_id
            LEFT JOIN instructors i ON ci.instructor_id = i.id
            WHERE c.courseCode = ?
              AND (c.year = ? OR c.year IS NULL)
              AND (c.term = ? OR c.term IS NULL)
            GROUP BY c.id
            ORDER BY c.seatsAvailable DESC
        """, (course_code, year, term))
        
        sections = cursor.fetchall()
        valid_sections = []
        
        # Process each section and manually filter by time constraints
        for section in sections:
            # Skip sections with no timing info
            if not section['startTime'] or not section['endTime'] or not section['days']:
                continue
                
            # Convert times to integers for comparison
            start_time = int(section['startTime'])
            end_time = int(section['endTime'])
            
            # Check time constraints
            if start_time < earliest_time_int:
                print(f"Skipping {course_code} section {section['section']} - starts too early: {section['startTime']}")
                continue
                
            if end_time > latest_time_int:
                print(f"Skipping {course_code} section {section['section']} - ends too late: {section['endTime']}")
                continue
                
            # Check day constraints
            if not any(day in preferred_days for day in section['days']):
                print(f"Skipping {course_code} section {section['section']} - no classes on preferred days")
                continue
                
            # This section meets all constraints
            valid_sections.append(dict(section))
            
        if valid_sections:
            course_sections[course_code] = valid_sections
            print(f"Found {len(valid_sections)} valid sections for {course_code}")
    
    # Check if we have sections for all required courses
    missing_required = [course for course in required_courses if course not in course_sections]
    if missing_required:
        conn.close()
        raise ValueError(f"No available sections found for required courses: {', '.join(missing_required)}")
    
    # Generate all possible combinations
    schedules = []
    
    # Start with required courses
    required_combinations = []
    for course in required_courses:
        if course in course_sections:
            sections = course_sections[course]
            if not required_combinations:
                required_combinations = [[section] for section in sections]
            else:
                new_combinations = []
                for combo in required_combinations:
                    for section in sections:
                        if not has_time_conflict(combo + [section]):
                            new_combinations.append(combo + [section])
                required_combinations = new_combinations
    
    # If no valid combinations of required courses, return empty list
    if required_courses and not required_combinations:
        conn.close()
        return []
    
    # If we have no required courses, start with an empty list
    if not required_combinations:
        required_combinations = [[]]
    
    # Add optional courses if possible
    optional_courses_available = [c for c in optional_courses if c in course_sections]
    remaining_slots = max_courses - len(required_courses)
    
    if remaining_slots > 0 and optional_courses_available:
        for r in range(1, min(remaining_slots + 1, len(optional_courses_available) + 1)):
            for opt_course_combo in itertools.combinations(optional_courses_available, r):
                # Create cartesian product of sections for these optional courses
                opt_section_combos = [course_sections[course] for course in opt_course_combo]
                for opt_sections in itertools.product(*opt_section_combos):
                    # For each base schedule of required courses
                    for req_combo in required_combinations:
                        # Check if this combo of optional sections works with required courses
                        candidate_schedule = req_combo + list(opt_sections)
                        if not has_time_conflict(candidate_schedule):
                            schedules.append({
                                'courses': candidate_schedule,
                                'score': calculate_schedule_score(candidate_schedule, prioritize_gaps)
                            })
    else:
        # Just use the required courses
        for req_combo in required_combinations:
            schedules.append({
                'courses': req_combo,
                'score': calculate_schedule_score(req_combo, prioritize_gaps)
            })
    
    conn.close()
    
    # Sort schedules by score (higher is better)
    schedules.sort(key=lambda s: s['score'], reverse=True)
    
    # Return top 10 schedules
    return schedules[:10]

def has_time_conflict(sections):
    """
    Check if there is a time conflict between the provided sections.
    
    Args:
        sections (list): List of course section dictionaries
    
    Returns:
        bool: True if there is a conflict, False otherwise
    """
    for i, section1 in enumerate(sections):
        # Skip sections without day or time information
        if not section1.get('days') or not section1.get('startTime') or not section1.get('endTime'):
            continue
            
        for j in range(i+1, len(sections)):
            section2 = sections[j]
            
            # Skip sections without day or time information
            if not section2.get('days') or not section2.get('startTime') or not section2.get('endTime'):
                continue
            
            # Check for day overlap
            common_days = set(section1['days']) & set(section2['days'])
            if not common_days:
                continue
            
            # Convert times to integers for better comparison
            try:
                start1 = time_to_minutes(section1['startTime'])
                end1 = time_to_minutes(section1['endTime'])
                start2 = time_to_minutes(section2['startTime'])
                end2 = time_to_minutes(section2['endTime'])
                
                # If end time is before start time (likely crossing midnight), 
                # adjust for 24-hour comparison
                if end1 < start1:
                    end1 += 24 * 60  # Add a day in minutes
                if end2 < start2:
                    end2 += 24 * 60
                
                # Check for time overlap
                if max(start1, start2) < min(end1, end2):
                    print(f"Time conflict detected between sections:")
                    print(f"  Section 1: {section1['courseCode']} {section1['section']} at {section1['startTime']}-{section1['endTime']} on {section1['days']}")
                    print(f"  Section 2: {section2['courseCode']} {section2['section']} at {section2['startTime']}-{section2['endTime']} on {section2['days']}")
                    return True
            except (ValueError, TypeError) as e:
                # If time conversion fails, be cautious and assume there might be a conflict
                print(f"Error comparing times: {e}")
                return True
                
    return False

def time_to_minutes(time_str):
    """Convert time in 'HHMM' format to minutes since midnight."""
    if not time_str or len(time_str) < 4:
        raise ValueError(f"Invalid time format: {time_str}")
    
    hours = int(time_str[:2])
    minutes = int(time_str[2:])
    
    return hours * 60 + minutes

def calculate_schedule_score(sections, prioritize_gaps):
    """
    Calculate a score for the schedule. Higher scores are better.
    
    Args:
        sections (list): List of course section dictionaries
        prioritize_gaps (bool): Whether to prioritize minimizing gaps
    
    Returns:
        float: Score for the schedule
    """
    score = 100.0  # Base score
    
    # Higher score for more courses
    score += len(sections) * 5
    
    # Prefer sections with more available seats
    available_seats_sum = sum(s.get('seatsAvailable', 0) for s in sections)
    score += min(available_seats_sum / 10, 10)  # Cap at 10 points
    
    # Prefer sections with known instructors
    instructor_score = sum(1 for s in sections if s.get('instructors'))
    score += instructor_score * 2
    
    if prioritize_gaps:
        try:
            # Calculate gaps between classes and penalize larger gaps
            daily_sections = {day: [] for day in "MTWRF"}
            
            for section in sections:
                # Skip if any required time info is missing
                if not section.get('days') or not section.get('startTime') or not section.get('endTime'):
                    continue
                    
                # Ensure days is a string we can iterate over
                days = section['days']
                if not isinstance(days, str):
                    continue
                
                # Convert times to integers safely
                try:
                    start_time = int(section['startTime'])
                    end_time = int(section['endTime'])
                except (ValueError, TypeError):
                    continue
                
                # Add time info for each day
                for day in days:
                    # Skip if not a valid day code
                    if day not in "MTWRF":
                        continue
                        
                    daily_sections[day].append({
                        'start': start_time,
                        'end': end_time
                    })
            
            # Calculate total gap minutes
            total_gap_minutes = 0
            for day, times in daily_sections.items():
                if len(times) >= 2:
                    # Sort by start time
                    times.sort(key=lambda x: x['start'])
                    
                    # Calculate gaps between consecutive classes
                    for i in range(len(times) - 1):
                        gap = times[i+1]['start'] - times[i]['end']
                        if gap > 0:
                            # Calculate hours and minutes more reliably
                            # For times in HHMM format: 
                            # - The hour difference is the first two digits of the gap
                            # - The minute difference is the last two digits
                            gap_str = str(gap).zfill(4)  # Ensure 4 digits with leading zeros
                            gap_hours = int(gap_str[:-2]) if len(gap_str) > 2 else 0
                            gap_minutes = int(gap_str[-2:])
                            
                            total_gap_minutes += gap_hours * 60 + gap_minutes
            
            # Penalize for gaps (more than 15 minutes)
            if total_gap_minutes > 15:
                score -= min(total_gap_minutes / 30, 20)  # Cap penalty at 20 points
                
        except Exception as e:
            # Log the error but don't fail - just don't apply gap penalties
            print(f"Error calculating gaps: {str(e)}")
    
    return score
