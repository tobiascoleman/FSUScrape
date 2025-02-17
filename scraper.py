import sqlite3
import requests
import init_db
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import time

def get_cookie(username, password, headless=True):
    """Scrapes a website with optional headless mode."""
    
    chrome_options = Options()
    if headless:
        # Set up Chrome options for headless mode
        chrome_options.add_argument("--headless=new")  # Run Chrome in headless mode
        chrome_options.add_argument("--disable-gpu")

    # Initialize WebDriver (Adjust the path if needed)
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)

    login_function(driver, username, password)

    # Navigate to the target page
    driver.get("https://fsu.collegescheduler.com/entry")
    WebDriverWait(driver, 10).until(lambda driver: driver.find_element(By.ID, "2024-fall-options"))

    cookies = driver.get_cookies()
    return cookies

def login_function(driver, username, password):
    driver.get("https://cas.fsu.edu/cas/login?service=https%3A%2F%2Fwww.my.fsu.edu%2Fc%2Fportal%2Flogin")
    userfield = driver.find_element(By.NAME, "username")
    passfield = driver.find_element(By.NAME, "password")
    userfield.send_keys(username)
    passfield.send_keys(password)
    
    login_button = driver.find_element(By.NAME, "submit")
    login_button.click()
    
    time.sleep(10)
    # print("page source", driver.page_source)
    if "Secured by Duo" in driver.page_source.strip():
            print("2FA detected! Please approve the login on your phone.")
            
            # Option 1: Wait for user confirmation manually
            input("Press ENTER once you have approved the login...")
                
    WebDriverWait(driver, 10).until(lambda driver: driver.find_element(By.ID, "dont-trust-browser-button")).click()
    WebDriverWait(driver, 10).until(lambda driver: driver.find_element(By.ID, "kgoui_Rcontent_I0_Rprimary_I0_Rcontent_I0_Rcontent"))
    

def fetch_course_data(year, term, subject, course, cookies):
    """Fetch course data from the API."""
    API_URL = f'https://fsu.collegescheduler.com/api/terms/{year}%20{term}/subjects/{subject}/courses/{course}/regblocks'
    HEADERS = {
        "Cookie": "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
    }
    try:
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

def create_database():
    """Create the SQLite database and tables if they don't exist."""
    with sqlite3.connect("fsu_courses.db") as conn:
        cursor = conn.cursor()

        # Create courses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                courseCode TEXT,
                section TEXT,
                seatsCapacity INTEGER,
                seatsAvailable INTEGER
            )
        """)

        # Create instructors table with a UNIQUE constraint on instructorName
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS instructors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instructorName TEXT UNIQUE
            )
        """)

        # Create a junction table to link courses and instructors
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS course_instructors (
                course_id INTEGER,
                instructor_id INTEGER,
                FOREIGN KEY (course_id) REFERENCES courses(id),
                FOREIGN KEY (instructor_id) REFERENCES instructors(id)
            )
        """)

        conn.commit()

def insert_course(course_code, section, seats_capacity, seats_available, instructors):
    """Insert a course into the database and link instructors."""
    try:
        # Convert seats_capacity to an integer if it's a string
        seats_capacity = int(seats_capacity)

        if seats_capacity > 0:
            conn = sqlite3.connect("fsu_courses.db")
            cursor = conn.cursor()

            # Insert the course
            cursor.execute("""
                INSERT INTO courses (courseCode, section, seatsCapacity, seatsAvailable)
                VALUES (?, ?, ?, ?)
            """, (course_code, section, seats_capacity, seats_available))
            course_id = cursor.lastrowid

            # Insert instructors and link them to the course
            for instructor in instructors:
                if isinstance(instructor, dict):
                    instructor_name = instructor.get("name", "Unknown")  # Default to 'Unknown' if no name found
                cursor.execute("""
                    INSERT INTO instructors (instructorName) 
                    VALUES (?)
                    ON CONFLICT(instructorName) DO NOTHING
                """, (instructor_name,))
                instructor_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO course_instructors (course_id, instructor_id)
                    VALUES (?, ?)
                """, (course_id, instructor_id))

            conn.commit()
            conn.close()
            print(f"Inserted: {course_code} - {section} (Seats: {seats_capacity}, Available: {seats_available}, Instructors: {instructors}")
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
