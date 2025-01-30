import sqlite3
import requests

# API URL and headers
API_URL = "https://fsu.collegescheduler.com/api/terms/2025%20Spring/subjects/BSC/courses/2011L/regblocks"
HEADERS = {
    "Cookie": "__RequestVerificationToken=Nz_CcLayA6_flup1rtR4XDg_Bdwcer301Mneo6OcK2b91gB_obVcBWKOxE4agl4rzWDoUKJgfe4pHdSQaSXGe85z8mM1; .AspNet.Cookies=xA9vZsdaIpn_vzG19OAlWfMpqKt7W72UBmqLRkEYh2WsDiHEYOWJ5lZbcz3d612I7BcbsYsQxQRCHowa4q4gkZ8304mx1rFADqjLwqLA6TdoiYmT88ihVg-lkAUiJlvbbYzJ4d1D7UvvBtG79ESATq0unijaO3IuSpY95eiAYoNwNOLDmukgLXGGEaEjSHaIMQgPrYkCOUuUAgGZfhfD9lYlTAO_hsorhIse6yLfrOcRUKyiy4QN3HwZJTz9eCDeWUNl0iFZXI8T2foL_tWMIuEhUnvNqAe5lhORKzaBW_UQM9qgFoALJMfu2JOeYGn8mWfD5pxHlneskUFIl2RxXjog23waYXWY0nM6sFvSIu4mtoL3hySBDvY8n0RwFrlKhfGCd8eTsq-2LzF0nOat3xUcf39ByIfJGNk8ke8e_X0doShJa1fUe7po30wVatXe_lse3V3EJzECiVBsAfHZHtou1Le7QSqnWewwlGfPwnT-buDFV9M40h57ZtoJMm3VcJr4MHMU0jDe5i5Ktf-W2jLz50RFyBrHhu8RVb8QrJIv1jhng9VEY3zMzb4YEokujoZ-0vamet9PQ-cK7gY_LlYlSB9247xZwGilVBC1U6zrd107OcFoFZBwb4zNBB5BLEFf09TV83cuI5D0R-_CK1cZqpNV_5SYfuGQivluRBTcDvHZcM1IrQEWTyOAiV94UOfA4oIOecku3f9Jn3_QyTw6lplSo-A_-hTNkUlzE0JFmZ3xOEG__nQOUxvUiv37yyOuYKL2RNv4r2k5xNKw2iJ4cx1RblkvP6I8hqJZ0WnHW_iCXPpcLlicVmGKpmERwMo1UkAwY7-4B7nACkNLaBmpq3aFdkxRqWe1e1aRVM36hCdCbhinVSHCxoWz_fm_EFJE3JCwy5myzY4ZD7wkBLOV6z12tjrFrVJlxcZgY2uiMehGqtZy57AD8cbBoM_jtVTiX2LbL2g-xjtfVMgWEzk7wN14I2BNBv2vqrc7MKu8ieYSPzRmjq78Ln_ZO27NiRP08JjO4Me1cyl8fsqEBBqNU1yfHpjjWXB078m6agefflDd2EAlUtp9s_1jIh4tf74NxSJoNDzYwqF9L5bLa98jKFZAbuUybF2unyg2awTAtejQIS_CPZ5tAl2pPy_OJDXO4X5imWg4MyirpXOsWxIbMARrsI7yxKs1n86-U5uBMYB0afeAr7CdUM9BeIpJPQ7M4u9ovoGboHhV3uFCu5oSByTwYHZjyJcQagD22Vl3nPy4fCz9OnqWh4DLDpozJCjNrtymPS1pbI1CIiJQo9cWKDWWv538zV9D1jPTVIg0Ic4gfic7AjpcIbr2vvSwg83nSPZs14oHrhMSxO-LSm21zlPVlqFk_sgfujISLQ5wvPAQHuCGZYhMjBuCsRs6CAkNRV6NTwl52pXxT2oWzrMcs9YQgegX8VHpfuZJCCfeq_Zf7EI_i5bgdrNJ6IzS1pnc9cN3mE4AQi0HXhPREByZ6i1MIXHu-yWvcRfCG4nEABNWl9VXJAfznKbcUxA9N4PFg5SFT3eRMmZsZY4U1A7NzrB3EsUzjM7JOk1QPQpiin_I1V7QPmUL6EQnHGXa8vzkOJOTDT2rCPT3oFjGeYgk4t4LksvxPbjBIe1UPBCh8qRo1UJYIt6irLvDVLo54vZgYGiEYnVsJhwyA0HrLedOZ8sezW7ylhAMBvYUZ_X8KqNFdvWZOFyvBH_BFqv66UolrzaCgtkWgy_YVoKqs1akma7dWoDjoBYzcL_1HGhsas-dDe_edPKESXB5t229A1uXlRgU-fHsEBt-LvQobkkKqXE"
}

def fetch_course_data():
    """Fetch course data from the API."""
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

def process_courses():
    """Fetch, parse, and insert course data into the database."""
    data = fetch_course_data()
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
    create_database()
    process_courses()