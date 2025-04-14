import sqlite3

"""Create the SQLite database and tables if they don't exist."""
def init_courses():
    with sqlite3.connect("fsu_courses.db") as conn:
        cursor = conn.cursor()

        # Create courses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                courseCode TEXT,
                section TEXT,
                seatsCapacity INTEGER,
                seatsAvailable INTEGER,
                days TEXT,
                startTime TEXT,
                endTime TEXT,
                location TEXT,
                year TEXT,
                term TEXT,
                UNIQUE(courseCode, section)
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitored_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                courseCode TEXT,      -- Subject code (e.g., 'MAC')
                section TEXT,         -- Combined course-section (e.g., '2311-001')
                year TEXT NOT NULL DEFAULT '2025',
                term TEXT NOT NULL DEFAULT 'Spring',
                FOREIGN KEY (username) REFERENCES users(username),
                UNIQUE(username, courseCode, section)
            )
        """)

        conn.commit()

def init_users():
    with sqlite3.connect("fsu_courses.db") as conn:
        cursor = conn.cursor()

        # Create users table with encrypted FSU password
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT UNIQUE PRIMARY KEY,
                password TEXT,
                fsu_password TEXT
            )
        """)

        conn.commit()

def init_schedules():
    """Initialize the tables for saved schedules."""
    with sqlite3.connect("fsu_courses.db") as conn:
        cursor = conn.cursor()
        
        # Create saved schedules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
        
        # Create saved schedule courses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                courseCode TEXT NOT NULL,
                section TEXT NOT NULL,
                FOREIGN KEY (schedule_id) REFERENCES saved_schedules(id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()

def init_db():
    """Initialize all tables in the database."""
    init_courses()
    init_users()
    init_schedules()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
