"""
Schedule Generator for FSU Course Scraper
Relies on SQL for efficient filtering and course selection
"""
import sqlite3
import itertools
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('schedule_generator')

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
    
    # Remove duplicates and get all candidate courses
    all_courses = list(set(required_courses + optional_courses))
    
    # Build a complex SQL query to filter courses directly in the database
    query = """
    SELECT c.*, 
           GROUP_CONCAT(i.instructorName) as instructors
    FROM courses c
    LEFT JOIN course_instructors ci ON c.id = ci.course_id
    LEFT JOIN instructors i ON ci.instructor_id = i.id
    WHERE c.courseCode = ?
      AND (c.year = ?)
      AND (c.term = ?)
      AND c.startTime >= ?
      AND c.endTime <= ?
      AND c.days IS NOT NULL
    """
    
    # Handle day preferences in SQL if possible
    day_filter = []
    for day in preferred_days:
        day_filter.append(f"c.days LIKE '%{day}%'")
    
    if day_filter:
        query += " AND (" + " OR ".join(day_filter) + ")"
    
    query += " GROUP BY c.id ORDER BY c.seatsAvailable DESC"
    
    # Get sections for each course using SQL filtering
    course_sections = {}
    for course_code in all_courses:
        logger.info(f"Querying sections for {course_code}")
        cursor.execute(query, (course_code, year, term, earliest_time, latest_time))
        sections = cursor.fetchall()
        
        # Convert sections to dictionaries for easier manipulation
        valid_sections = [dict(section) for section in sections]
        
        # Final day filtering in Python (for complex cases)
        filtered_sections = []
        for section in valid_sections:
            # Ensure there's at least one common day between section days and preferred days
            section_days = section['days'] or ""
            if any(day in preferred_days for day in section_days):
                filtered_sections.append(section)
        
        if filtered_sections:
            course_sections[course_code] = filtered_sections
            logger.info(f"Found {len(filtered_sections)} valid sections for {course_code}")
        else:
            logger.warning(f"No valid sections found for {course_code}")
    
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
                
                # Check for time overlap
                if max(start1, start2) < min(end1, end2):
                    logger.debug(f"Time conflict detected between sections:")
                    logger.debug(f"  Section 1: {section1['courseCode']} {section1['section']} at {section1['startTime']}-{section1['endTime']} on {section1['days']}")
                    logger.debug(f"  Section 2: {section2['courseCode']} {section2['section']} at {section2['startTime']}-{section2['endTime']} on {section2['days']}")
                    return True
            except (ValueError, TypeError) as e:
                # If time conversion fails, be cautious and assume there might be a conflict
                logger.warning(f"Error comparing times: {e}")
                return True
                
    return False

def time_to_minutes(time_str):
    """Convert time in 'HHMM' or 'HMM' format to minutes since midnight."""
    if not time_str:
        raise ValueError(f"Empty time string")
        
    # Convert to string if it's not already
    time_str = str(time_str).strip()
    
    # Handle 3-digit format (e.g., "800" for 8:00 AM)
    if len(time_str) == 3:
        hours = int(time_str[0])
        minutes = int(time_str[1:])
    # Handle 4-digit format (e.g., "0800" or "1430")
    elif len(time_str) == 4:
        hours = int(time_str[:2])
        minutes = int(time_str[2:])
    else:
        raise ValueError(f"Invalid time format: {time_str}")
    
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
                    start_time = time_to_minutes(section['startTime'])
                    end_time = time_to_minutes(section['endTime'])
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
                            total_gap_minutes += gap
            
            # Penalize for gaps (more than 15 minutes)
            if total_gap_minutes > 15:
                score -= min(total_gap_minutes / 30, 20)  # Cap penalty at 20 points
                
        except Exception as e:
            # Log the error but don't fail - just don't apply gap penalties
            logger.error(f"Error calculating gaps: {str(e)}")
    
    return score

# For testing
if __name__ == "__main__":
    import sys
    
    # Simple CLI for testing
    print("Schedule Generator Test")
    required = input("Required courses (comma-separated): ").split(",")
    optional = input("Optional courses (comma-separated): ").split(",")
    start_time = input("Earliest time (HHMM format, e.g. 0800): ")
    end_time = input("Latest time (HHMM format, e.g. 1700): ")
    days = input("Preferred days (e.g. MWF): ")
    max_count = int(input("Maximum number of courses: "))
    year = input("Year (e.g. 2025): ")
    term = input("Term (e.g. Fall): ")
    
    required = [c.strip() for c in required if c.strip()]
    optional = [c.strip() for c in optional if c.strip()]
    
    try:
        schedules = generate_optimal_schedules(
            required, optional, start_time, end_time, 
            days, max_count, year, term, True, "test_user"
        )
        
        print(f"Generated {len(schedules)} schedules:")
        for i, schedule in enumerate(schedules[:5]):
            print(f"\nSchedule {i+1} (Score: {schedule['score']:.2f}):")
            for course in schedule['courses']:
                print(f"  {course['courseCode']}-{course['section']} {course['days']} {course['startTime']}-{course['endTime']} ({course.get('instructors', 'No instructor')})")
    except Exception as e:
        print(f"Error: {e}")
