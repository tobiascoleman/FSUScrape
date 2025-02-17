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

def init_db():
    """Initialize all tables in the database."""
    init_courses()
    init_users()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
