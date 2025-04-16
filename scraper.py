"""
FSU Course Scraper - Core scraping functionality

This module handles fetching course data from FSU's College Scheduler API,
processing it, and storing it in the database. It also handles monitoring
courses for seat availability.
"""

import sqlite3
import requests
import time
import threading
import logging
from encryption import cipher
from auth_manager import get_valid_cookies, clear_cookie_cache

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('scraper')

# API Constants
FSU_API_BASE = 'https://fsu.collegescheduler.com/api'
DB_PATH = "fsu_courses.db"

def fetch_course_data(year, term, subject, course, username=None, password=None, retry=True):
    """
    Fetch course data from FSU's College Scheduler API.
    
    Args:
        year: The academic year (e.g., 2025)
        term: The academic term (e.g., Fall, Spring)
        subject: The course subject code (e.g., MAT)
        course: The course number (e.g., 1033)
        username: FSU username for authentication (optional)
        password: FSU password for authentication (optional)
        retry: Whether to retry on failure (default True)
        
    Returns:
        JSON response data or None if request fails
    """
    try:
        api_url = f'{FSU_API_BASE}/terms/{year}%20{term}/subjects/{subject}/courses/{course}/regblocks'
        logger.info(f"Fetching data for {subject}{course} {term} {year}")
        
        # Get authentication cookies if credentials provided
        cookies = None
        if username and password:
            logger.info(f"Getting authentication cookies for {username}")
            
            # CRITICAL DEBUG: Add more diagnostic logging
            logger.info(f"Starting cookie retrieval process for {username}")
            start_time = time.time()
            
            cookies = get_valid_cookies(username, password)
            
            end_time = time.time()
            logger.info(f"Cookie retrieval completed in {end_time - start_time:.2f}s. Success: {cookies is not None}")
            
        if not cookies:
            logger.warning("No valid cookies obtained, request will likely fail")
            return None
            
        # Make API request with cookies
        headers = {
            "Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Successfully fetched data for {subject}{course}")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        
        # Only retry if this wasn't already a retry attempt
        if retry and username and password:
            logger.info("Attempting to refresh cookies and retry...")
            clear_cookie_cache(username)
            
            try:
                cookies = get_valid_cookies(username, password, force_refresh=True)
                return fetch_course_data(year, term, subject, course, username, password, retry=False)
            except Exception as retry_error:
                logger.error(f"Retry failed: {retry_error}")
                
        return None
    except Exception as e:
        logger.error(f"Unexpected error in fetch_course_data: {e}")
        return None

def get_db_connection():
    """Get a connection to the SQLite database with foreign key support."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def insert_course(course_code, section, seats_capacity, seats_available, instructors, days, 
                 start_time, end_time, location, year, term):
    """
    Insert or update a course in the database.
    
    Args:
        course_code: The course code (e.g., MAT1033)
        section: The section number (e.g., 0001)
        seats_capacity: Total number of seats
        seats_available: Number of available seats
        instructors: List of instructor dictionaries
        days: String representation of meeting days (e.g., "MWF")
        start_time: Start time in HHMM format (e.g., "0900")
        end_time: End time in HHMM format (e.g., "0950")
        location: Classroom location
        year: Academic year
        term: Academic term
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate seat capacity
        seats_capacity = int(seats_capacity)
        if seats_capacity <= 0:
            logger.info(f"Skipped {course_code}-{section} (No available seats)")
            return False

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Check if course exists
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
                cursor.execute("DELETE FROM course_instructors WHERE course_id = ?", (course_id,))
                action = "Updated"
            else:
                # Insert new course
                cursor.execute("""
                    INSERT INTO courses (courseCode, section, seatsCapacity, seatsAvailable, 
                                       days, startTime, endTime, location, year, term)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (course_code, section, seats_capacity, seats_available, 
                     days, start_time, end_time, location, year, term))
                course_id = cursor.lastrowid
                action = "Inserted"

            # Insert/update instructors
            if instructors:
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
            logger.info(f"{action}: {course_code}-{section} ({seats_available}/{seats_capacity} seats) " +
                      f"{days or 'N/A'} {start_time or 'TBA'}-{end_time or 'TBA'} @ {location or 'TBA'}")
            return True

        except sqlite3.Error as db_error:
            conn.rollback()
            logger.error(f"Database error for {course_code}-{section}: {db_error}")
            return False
        finally:
            conn.close()

    except ValueError:
        logger.error(f"Invalid seats_capacity value for {course_code}-{section}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error inserting {course_code}-{section}: {e}")
        return False

def process_courses(data, year, term):
    """
    Process course data and insert it into the database.
    
    Args:
        data: JSON data from the API
        year: The academic year
        term: The academic term
        
    Returns:
        Number of courses processed
    """
    if not data:
        logger.warning("No data to process")
        return 0
        
    courses_processed = 0
    
    try:
        if 'sections' not in data:
            logger.error(f"Invalid data format - 'sections' field missing: {data}")
            return 0
            
        for course in data['sections']:
            # Skip non-main campus courses
            if course.get("campusCode", "MAIN") != "MAIN":
                continue
                
            # Extract basic course details
            course_code = course.get("course", "Unknown")
            subject_id = course.get("subjectId", "Unknown")
            section_code = course.get("sectionNumber", "Unknown")
            seats_capacity = course.get("seatsCapacity", 0)
            seats_available = course.get("openSeats", 0)
            instructor_list = course.get("instructor", "Unknown")
            
            # Default values for meeting details
            days = start_time = end_time = location = None
            
            # Extract meeting details if available
            if "meetings" in course and course["meetings"] and len(course["meetings"]) > 0:
                meeting = course["meetings"][0]
                days = meeting.get("days")
                start_time = meeting.get("startTime")
                end_time = meeting.get("endTime")
                location = meeting.get("location")
            
            # Ensure capacity is an integer and >0
            try:
                seats_capacity = int(seats_capacity)
                if seats_capacity <= 0:
                    continue
            except (ValueError, TypeError):
                logger.warning(f"Invalid seats capacity for {subject_id}{course_code}-{section_code}: {seats_capacity}")
                continue
                
            # Form the complete course code
            complete_course_code = f"{subject_id}{course_code}"
            
            # Insert into database
            success = insert_course(
                complete_course_code, section_code, seats_capacity, seats_available,
                instructor_list, days, start_time, end_time, location, year, term
            )
            
            if success:
                courses_processed += 1
                
        logger.info(f"Processed {courses_processed} courses for {term} {year}")
        return courses_processed
        
    except Exception as e:
        logger.error(f"Error processing courses: {e}")
        return courses_processed

def check_monitored_courses():
    """
    Periodically check monitored courses for seat availability.
    
    This function runs in a separate thread and continuously checks if seats
    have become available in any monitored courses.
    """
    # Import here to avoid circular imports
    from app import send_notification
    
    logger.info("Starting monitored courses checker thread")
    
    while True:
        try:
            # Get all users with monitored courses
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT mc.username, u.fsu_password as encrypted_password
                FROM monitored_courses mc
                JOIN users u ON mc.username = u.username
            """)
            users = cursor.fetchall()
            
            for username, encrypted_password in users:
                try:
                    # Decrypt password
                    password = cipher.decrypt(encrypted_password)
                    
                    # Get this user's monitored courses
                    cursor.execute("""
                        SELECT mc.courseCode, mc.section, mc.year, mc.term
                        FROM monitored_courses mc
                        WHERE mc.username = ?
                        ORDER BY mc.courseCode, mc.section
                    """, (username,))
                    user_courses = cursor.fetchall()
                    
                    logger.info(f"Checking {len(user_courses)} courses for user {username}")
                    
                    # Get cookies once for this user
                    try:
                        cookies = get_valid_cookies(username, password)
                        if not cookies:
                            logger.warning(f"Failed to get valid cookies for {username}")
                            continue
                            
                        # Check each course
                        for course_code, section, year, term in user_courses:
                            try:
                                # Extract subject and course number
                                subject = ''.join(filter(str.isalpha, course_code))
                                course_num = ''.join(filter(str.isdigit, course_code))
                                
                                # Make API request
                                api_url = f'{FSU_API_BASE}/terms/{year}%20{term}/subjects/{subject}/courses/{course_num}/regblocks'
                                headers = {
                                    "Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
                                }
                                
                                response = requests.get(api_url, headers=headers, timeout=10)
                                response.raise_for_status()
                                data = response.json()
                                
                                # Check for open seats
                                if data and 'sections' in data:
                                    for course_section in data['sections']:
                                        if course_section['sectionNumber'] == section:
                                            open_seats = course_section.get('openSeats', 0)
                                            if open_seats > 0:
                                                # Seats available! Send notification
                                                message = (f"Seat available in {course_code} "
                                                         f"section {section}! "
                                                         f"Available seats: {open_seats}")
                                                logger.info(f"SEATS AVAILABLE: {message}")
                                                send_notification(username, message)
                                                
                                                # Update course in database
                                                update_course_availability(course_code, section, 
                                                                          course_section.get('seatsCapacity', 0), 
                                                                          open_seats)
                                            break
                                    
                            except Exception as course_error:
                                logger.error(f"Error checking {course_code}-{section}: {course_error}")
                                continue
                                
                    except Exception as auth_error:
                        logger.error(f"Authentication error for {username}: {auth_error}")
                        clear_cookie_cache(username)
                    
                except Exception as user_error:
                    logger.error(f"Error processing user {username}: {user_error}")
                    
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in course monitoring: {e}")
            
        # Wait before next check
        time.sleep(30)

def update_course_availability(course_code, section, capacity, available):
    """Update course availability in the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE courses 
            SET seatsCapacity = ?, seatsAvailable = ?
            WHERE courseCode = ? AND section = ?
        """, (capacity, available, course_code, section))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Updated availability for {course_code}-{section}: {available}/{capacity}")
        return True
    except Exception as e:
        logger.error(f"Failed to update availability for {course_code}-{section}: {e}")
        return False

# Main execution block
if __name__ == "__main__":
    import init_db
    
    # Initialize the database
    init_db.init_db()
    
    # Simple command-line interface for testing
    username = input("FSU username: ")
    password = input("FSU password: ")
    year = input("Year (e.g., 2025): ")
    term = input("Term (e.g., Fall): ")
    subject = input("Subject code (e.g., MAT): ")
    course = input("Course number (e.g., 1033): ")
    
    # Fetch and process course data
    data = fetch_course_data(year, term, subject, course, username, password)
    if data:
        print(f"Found {len(data.get('sections', []))} sections")
        process_courses(data, year, term)
    else:
        print("No data fetched")
        
    # Manual test of monitoring
    start_monitor = input("Start monitoring thread? (y/n): ")
    if start_monitor.lower() == 'y':
        monitor_thread = threading.Thread(target=check_monitored_courses, daemon=True)
        monitor_thread.start()
        
        try:
            print("Press Ctrl+C to exit...")
            # Keep main thread alive while daemon thread runs
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nExiting...")
