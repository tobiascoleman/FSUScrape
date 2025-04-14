import queue
import sqlite3
import requests
import init_db
from encryption import cipher
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import time
import threading

# Global cookie cache
COOKIE_CACHE = {}

def get_cookie(username, password, headless=True, auth_queue=None, force_refresh=False, notify_callback=None):
    """Get cookies from cache or fetch new ones."""
    global COOKIE_CACHE
    
    if not force_refresh and username in COOKIE_CACHE:
        return COOKIE_CACHE[username]
    
    if notify_callback:
        notify_callback(username, "2FA authentication required. Please check your phone.")
        
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        login_function(driver, username, password, auth_queue)
        driver.get("https://fsu.collegescheduler.com/entry")
        WebDriverWait(driver, 20).until(lambda driver: driver.find_element(By.ID, "2024-fall-options"))
        cookies = driver.get_cookies()
        COOKIE_CACHE[username] = cookies
        return cookies
    finally:
        driver.quit()

def login_function(driver, username, password, auth_queue=None):
    driver.get("https://cas.fsu.edu/cas/login?service=https%3A%2F%2Fwww.my.fsu.edu%2Fc%2Fportal%2Flogin")
    userfield = driver.find_element(By.NAME, "username")
    passfield = driver.find_element(By.NAME, "password")
    userfield.send_keys(username)
    passfield.send_keys(password)
    
    login_button = driver.find_element(By.NAME, "submit")
    login_button.click()
    
    time.sleep(10)
    if "Secured by Duo" in driver.page_source.strip():
        print("2FA detected! Please approve the login on your phone.")
        max_wait = 60  # Maximum wait time in seconds
        start_time = time.time()
        
        while "Secured by Duo" in driver.page_source.strip():
            time.sleep(2)  # Check every 2 seconds
            if time.time() - start_time > max_wait:
                raise Exception("2FA timeout after 60 seconds")
        
        print("2FA approved!")
        # Inject JavaScript to close the loading screen
        driver.execute_script("window.parent.postMessage('2fa_approved', '*');")
    else:
        driver.execute_script("window.parent.postMessage('2fa_approved', '*');")
    WebDriverWait(driver, 20).until(lambda driver: driver.find_element(By.ID, "dont-trust-browser-button")).click()
    WebDriverWait(driver, 20).until(lambda driver: driver.find_element(By.ID, "kgoui_Rcontent_I0_Rprimary_I0_Rcontent_I0_Rcontent"))

def fetch_course_data(year, term, subject, course, cookies, username=None, password=None, retry=True):
    """Fetch course data from the API with automatic cookie refresh."""
    global COOKIE_CACHE
    
    try:
        API_URL = f'https://fsu.collegescheduler.com/api/terms/{year}%20{term}/subjects/{subject}/courses/{course}/regblocks'
        HEADERS = {
            "Cookie": "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
        }
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        # If this was already a retry attempt, or we don't have credentials to retry, give up
        if not retry or not username or not password:
            if username and username in COOKIE_CACHE:
                del COOKIE_CACHE[username]
            return None
            
        print("Attempting to refresh cookies and retry...")
        # Clear cached cookies and get fresh ones
        if username in COOKIE_CACHE:
            del COOKIE_CACHE[username]
        
        try:
            # Get fresh cookies and retry the request once
            new_cookies = get_cookie(username, password, headless=True, force_refresh=True)
            return fetch_course_data(year, term, subject, course, new_cookies, username, password, retry=False)
        except Exception as retry_error:
            print(f"Retry failed: {retry_error}")
            return None

def insert_course(course_code, section, seats_capacity, seats_available, instructors):
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
                    SET seatsCapacity = ?, seatsAvailable = ?
                    WHERE courseCode = ? AND section = ?
                """, (seats_capacity, seats_available, course_code, section))
                course_id = existing_course[0]
                
                # Remove old instructor links
                cursor.execute("""
                    DELETE FROM course_instructors 
                    WHERE course_id = ?
                """, (course_id,))
            else:
                # Insert new course
                cursor.execute("""
                    INSERT INTO courses (courseCode, section, seatsCapacity, seatsAvailable)
                    VALUES (?, ?, ?, ?)
                """, (course_code, section, seats_capacity, seats_available))
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
            print(f"{action}: {course_code} - {section} (Seats: {seats_capacity}, Available: {seats_available}, Instructors: {instructors}")
        else:
            print(f"Skipped {course_code} - {section} (No available seats)")

    except ValueError:
        print(f"Invalid seatsCapacity value for {course_code} - {section}")

def process_courses(data):
    """Fetch, parse, and insert course data into the database."""
    if data:
        if 'sections' in data:
            for course in data['sections']:
                # Extract course details from the section
                course_code = course.get("course", "Unknown")
                subject_id = course.get("subjectId", "Unkown")
                section_code = course.get("sectionNumber", "Unknown")
                seats_capacity = course.get("seatsCapacity", 0)
                seats_available = course.get("seatsAvailable", 0)
                instructorList = course.get("instructor", "Unknown")
                    
                # Insert only if seatsCapacity > 0
                seats_capacity = int(seats_capacity)
                if seats_capacity > 0:
                    course_code = subject_id + course_code
                    print(course_code)
                    insert_course(course_code, section_code, seats_capacity, seats_available, instructorList)
        else:
            print(f"Invalid or missing 'sections' in field: {data}")
    else:
        print("No data fetched.")

def check_monitored_courses(notify_callback=None):
    """Check monitored courses for availability."""
    global COOKIE_CACHE
    
    while True:
        conn = sqlite3.connect("fsu_courses.db")
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT mc.username, mc.courseCode, mc.section, u.fsu_password as encrypted_password
            FROM monitored_courses mc
            JOIN users u ON mc.username = u.username
        """)
        monitored = cursor.fetchall()
        conn.close()
        
        for username, course_code, section, encrypted_password in monitored:
            try:
                subject = ''.join(filter(str.isalpha, course_code))
                course_num = ''.join(filter(str.isdigit, course_code))
                password = cipher.decrypt(encrypted_password)
                
                # First attempt with cached cookies
                cookies = get_cookie(username, password, headless=True)
                data = fetch_course_data("2024", "Spring", subject, course_num, cookies, username, password)
                
                # If data fetch failed, try one more time with fresh cookies
                if not data:
                    print(f"Refreshing cookies for {username}...")
                    if username in COOKIE_CACHE:
                        del COOKIE_CACHE[username]
                    try:
                        cookies = get_cookie(username, password, headless=True, force_refresh=True, notify_callback=notify_callback)
                        data = fetch_course_data("2024", "Spring", subject, course_num, cookies, username, password, retry=False)
                    except Exception as e:
                        print(f"Failed to refresh cookies: {e}")
                        continue
                
                if data and 'sections' in data:
                    # Look for the specific section number
                    for course_section in data['sections']:
                        if course_section['sectionNumber'] == section:
                            if course_section['seatsCapacity'] > 0:
                                message = (f"Seat available in {course_code} "
                                         f"section {section}! "
                                         f"Available seats: {course_section['seatsAvailable']}")
                                print(message)
                                if notify_callback:
                                    notify_callback(username, message)
                            break
                else:
                    print(f"Failed to fetch data for {course_code} after cookie refresh")
                
            except Exception as e:
                print(f"Error checking {course_code} section {section}: {str(e)}")
                # Clear cached cookies on error
                if username in COOKIE_CACHE:
                    del COOKIE_CACHE[username]
        
        time.sleep(30)

if __name__ == "__main__":
    init_db.init_db()
    username = input("username: ")
    password = input("password: ")
    year = input("year: ")
    term = input("term: ")
    subject = input("subject: ")
    course = input("course: ")
    cookies = get_cookie(username, password, headless=False)  # Set to False for testing
    data = fetch_course_data(year, term, subject, course, cookies)
    print(data)
    if not data:
        print("No data fetched...")
    process_courses(data)
    
    # Start monitoring thread
    monitor_thread = threading.Thread(target=check_monitored_courses, daemon=True)
    monitor_thread.start()
