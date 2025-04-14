import queue
import sqlite3
import requests
import init_db
from encryption import cipher
import time
import threading
from auth_manager import get_valid_cookies, clear_cookie_cache

def fetch_course_data(year, term, subject, course, username=None, password=None, retry=True, notify_callback=None):
    """Fetch course data from the API with automatic cookie refresh."""
    
    try:
        API_URL = f'https://fsu.collegescheduler.com/api/terms/{year}%20{term}/subjects/{subject}/courses/{course}/regblocks'
        
        # Get cookies (will be cached if valid)
        cookies = get_valid_cookies(username, password, notify_callback) if username and password else None
        if not cookies:
            return None
            
        # Fixed syntax error in list comprehension
        HEADERS = {
            "Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
        }
        
        response = requests.get(API_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        # If this was already a retry attempt, or we don't have credentials to retry, give up
        if not retry or not username or not password:
            clear_cookie_cache(username)
            return None
            
        print("Attempting to refresh cookies and retry...")
        # Clear cached cookies and get fresh ones
        clear_cookie_cache(username)
        
        try:
            # Get fresh cookies and retry the request once
            cookies = get_valid_cookies(username, password, notify_callback, force_refresh=True)
            return fetch_course_data(year, term, subject, course, username, password, retry=False, notify_callback=notify_callback,)
        except Exception as retry_error:
            print(f"Retry failed: {retry_error}")
            return None

def insert_course(course_code, section, seats_capacity, seats_available, instructors, days, start_time, end_time, location, year, term):
    """Insert or update a course in the database and link instructors."""
    try:
        seats_capacity = int(seats_capacity)

        if seats_capacity > 0:
            conn = sqlite3.connect("fsu_courses.db")
            cursor = conn.cursor()

            # First, try to find existing course
            cursor.execute("""
                SELECT id FROM courses 
                WHERE courseCode = ? AND section = ?
            """, (course_code, section))
            existing_course = cursor.fetchone()

            if existing_course:
                # Update existing course
                cursor.execute("""
                    UPDATE courses 
                    SET seatsCapacity = ?, seatsAvailable = ?, 
                        days = ?, startTime = ?, endTime = ?, location = ?,
                        year = ?, term = ?
                    WHERE courseCode = ? AND section = ?
                """, (seats_capacity, seats_available, days, start_time, end_time, 
                      location, year, term, course_code, section))
                course_id = existing_course[0]
                
                # Remove old instructor links
                cursor.execute("""
                    DELETE FROM course_instructors 
                    WHERE course_id = ?
                """, (course_id,))
            else:
                # Insert new course
                cursor.execute("""
                    INSERT INTO courses (courseCode, section, seatsCapacity, seatsAvailable, 
                                       days, startTime, endTime, location, year, term)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (course_code, section, seats_capacity, seats_available, 
                     days, start_time, end_time, location, year, term))
                course_id = cursor.lastrowid

            # Insert/update instructors and link them to the course
            for instructor in instructors:
                if isinstance(instructor, dict):
                    instructor_name = instructor.get("name", "Unknown")
                    cursor.execute("""
                        INSERT INTO instructors (instructorName) 
                        VALUES (?)
                        ON CONFLICT(instructorName) DO UPDATE SET 
                        instructorName = excluded.instructorName
                        RETURNING id
                    """, (instructor_name,))
                    instructor_result = cursor.fetchone()
                    instructor_id = instructor_result[0]

                    cursor.execute("""
                        INSERT INTO course_instructors (course_id, instructor_id)
                        VALUES (?, ?)
                    """, (course_id, instructor_id))

            conn.commit()
            conn.close()
            action = "Updated" if existing_course else "Inserted"
            print(f"{action}: {course_code} - {section} (Seats: {seats_capacity}, Available: {seats_available}, Schedule: {days} {start_time}-{end_time} at {location} for {term} {year})")
        else:
            print(f"Skipped {course_code} - {section} (No available seats)")

    except ValueError:
        print(f"Invalid seatsCapacity value for {course_code} - {section}")

def process_courses(data, year, term):
    """Fetch, parse, and insert course data into the database."""
    if data:
        if 'sections' in data:
            for course in data['sections']:
                if course.get("location") != "Main, Tallahassee":
                    break
                # Extract course details from the section
                course_code = course.get("course", "Unknown")
                subject_id = course.get("subjectId", "Unkown")
                section_code = course.get("sectionNumber", "Unknown")
                seats_capacity = course.get("seatsCapacity", 0)
                seats_available = course.get("openSeats", 0)
                instructorList = course.get("instructor", "Unknown")
                                
                if "meetings" in course and course["meetings"] and len(course["meetings"]) > 0:
                    meeting = course["meetings"][0]
                    days = meeting.get("days")
                    start_time = meeting.get("startTime")
                    end_time = meeting.get("endTime")
                    location = meeting.get("location")
                
                # Insert only if seatsCapacity > 0
                seats_capacity = int(seats_capacity)
                if seats_capacity > 0:
                    course_code = subject_id + course_code
                    print(course_code)
                    insert_course(
                        course_code, section_code, seats_capacity, seats_available, 
                        instructorList, days, start_time, end_time, location, 
                        year, term  # Pass year and term
                    )
        else:
            print(f"Invalid or missing 'sections' in field: {data}")
    else:
        print("No data fetched.")

def check_monitored_courses(notify_callback=None):
    """Check monitored courses for availability."""
    
    while True:
        # Group monitored courses by username to minimize authentication requests
        conn = sqlite3.connect("fsu_courses.db")
        cursor = conn.cursor()
        
        # First, get all users with monitored courses
        cursor.execute("""
            SELECT DISTINCT mc.username, u.fsu_password as encrypted_password
            FROM monitored_courses mc
            JOIN users u ON mc.username = u.username
        """)
        users = cursor.fetchall()
        
        for username, encrypted_password in users:
            try:
                password = cipher.decrypt(encrypted_password)
                
                # Get courses for this user
                cursor.execute("""
                    SELECT mc.courseCode, mc.section, mc.year, mc.term
                    FROM monitored_courses mc
                    WHERE mc.username = ?
                    ORDER BY mc.courseCode, mc.section
                """, (username,))
                user_courses = cursor.fetchall()
                
                print(f"Checking {len(user_courses)} courses for user {username}")
                
                # Try to get valid cookies for this user once
                try:
                    # This will use cached cookies if available
                    cookies = get_valid_cookies(username, password, notify_callback=notify_callback)
                    
                    # Now check all courses with these cookies
                    for course_code, section, year, term in user_courses:
                        try:
                            subject = ''.join(filter(str.isalpha, course_code))
                            course_num = ''.join(filter(str.isdigit, course_code))
                            
                            print(f"Checking {course_code} section {section} for {year} {term}")
                            
                            # Direct API call using the cookies we already validated
                            API_URL = f'https://fsu.collegescheduler.com/api/terms/{year}%20{term}/subjects/{subject}/courses/{course_num}/regblocks'
                            HEADERS = {
                                "Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
                            }
                            
                            response = requests.get(API_URL, headers=HEADERS, timeout=10)
                            response.raise_for_status()
                            data = response.json()
                            
                            if data and 'sections' in data:
                                # Look for the specific section number
                                for course_section in data['sections']:
                                    if course_section['sectionNumber'] == section:
                                        if course_section['openSeats'] > 0:
                                            message = (f"Seat available in {course_code} "
                                                     f"section {section}! "
                                                     f"Available seats: {course_section['openSeats']}")
                                            print(message)
                                            if notify_callback:
                                                notify_callback(username, message)
                                        break
                            
                        except Exception as course_error:
                            print(f"Error checking {course_code} section {section}: {str(course_error)}")
                            continue
                            
                except Exception as auth_error:
                    print(f"Authentication error for {username}: {str(auth_error)}")
                    # Clear cached cookies on error
                    clear_cookie_cache(username)
                
            except Exception as user_error:
                print(f"Error processing courses for {username}: {str(user_error)}")
                continue
        
        conn.close()
        time.sleep(30)  # Check every 30 seconds

if __name__ == "__main__":
    init_db.init_db()
    username = input("username: ")
    password = input("password: ")
    year = input("year: ")
    term = input("term: ")
    subject = input("subject: ")
    course = input("course: ")
    
    data = fetch_course_data(year, term, subject, course, username, password)
    print(data)
    if not data:
        print("No data fetched...")
    process_courses(data)
    
    # Start monitoring thread
    monitor_thread = threading.Thread(target=check_monitored_courses, daemon=True)
    monitor_thread.start()
