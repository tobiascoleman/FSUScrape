from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import init_db
import scraper
from encryption import cipher
import threading
import time
from schedule_generator import generate_optimal_schedules
import auth_manager
from auth_manager import clear_auth_state
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'GONOLES!'

# Use a simpler scheduler without Flask-APScheduler
# This ensures the scheduler runs in the same process/thread context
scheduler = BackgroundScheduler()

def init_scheduler_job():
    """Add the monitoring job to the scheduler"""
    if not scheduler.get_job('check_monitored_courses'):
        scheduler.add_job(
            id='check_monitored_courses',
            func=scraper.check_monitored_courses,
            trigger='interval',
            seconds=30,
            max_instances=1,  # Prevent overlapping runs
            misfire_grace_time=10  # Allow job to be late by 10 seconds
        )
        print("Added check_monitored_courses job to scheduler (runs every 30 seconds)")

# Use before_first_request as a fallback for older Flask versions
@app.before_first_request
def init_scheduler():
    """Initialize scheduler after first request (for older Flask versions)"""
    if not scheduler.running:
        init_scheduler_job()
        scheduler.start()
        print("Scheduler started from before_first_request handler")

# Register a function to shut down the scheduler when the app exits
atexit.register(lambda: scheduler.shutdown(wait=False))

def get_db_connection():
    """Create a database connection with row factory enabled"""
    conn = sqlite3.connect('fsu_courses.db')
    conn.row_factory = sqlite3.Row
    return conn

# Basic route handlers
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hash password for app login
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        # Encrypt password for FSU login
        encrypted_fsu_password = cipher.encrypt(password.encode())

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, fsu_password) VALUES (?, ?, ?)", 
                         (username, hashed_password, encrypted_fsu_password))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists!', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Get the user's monitored courses
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mc.id, mc.courseCode, mc.section, c.seatsCapacity, c.seatsAvailable, 
               c.days, c.startTime, c.endTime, c.location, c.year, c.term,
               GROUP_CONCAT(i.instructorName) as instructors
        FROM monitored_courses mc
        LEFT JOIN courses c ON mc.courseCode = c.courseCode AND mc.section = c.section
        LEFT JOIN course_instructors ci ON c.id = ci.course_id
        LEFT JOIN instructors i ON ci.instructor_id = i.id
        WHERE mc.username = ?
        GROUP BY mc.id
        ORDER BY mc.courseCode
    """, (session['username'],))
    
    monitored_courses = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard.html', monitored_courses=monitored_courses)

# Course management routes
@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    """Add a course to the database"""
    if 'username' not in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        # Extract form data
        year = request.form['year']
        term = request.form['term']
        subject = request.form['subject']
        course = request.form['course']
        username = session['username']
        
        # Keep the clear_auth_state call for backward compatibility
        # It's now a no-op but keeping the call structure is cleaner than removing it
        clear_auth_state(username)
        
        # Get user's FSU password
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fsu_password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            flash('User not found!', 'danger')
            return redirect(url_for('dashboard'))
        
        try:
            # Decrypt password and fetch course data
            decrypted_password = cipher.decrypt(user['fsu_password'])
            data = scraper.fetch_course_data(year, term, subject, course, username, decrypted_password)
            
            if not data:
                flash('Failed to fetch course data. Please try again.', 'danger')
                return redirect(url_for('dashboard'))
            
            # Process the data
            scraper.process_courses(data, year, term)
            flash(f'Course data processed successfully for {subject}{course} {term} {year}!', 'success')
            
        except Exception as e:
            flash(f'Error processing course: {str(e)}', 'danger')
            
        return redirect(url_for('dashboard'))
        
    return render_template('add_course.html')

@app.route('/view_courses')
def view_courses():
    """View all courses in the database"""
    if 'username' not in session:
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get courses with monitored status for this user
    cursor.execute("""
        SELECT c.*, GROUP_CONCAT(i.instructorName) as instructors,
               CASE WHEN mc.id IS NOT NULL THEN 1 ELSE 0 END as is_monitored
        FROM courses c
        LEFT JOIN course_instructors ci ON c.id = ci.course_id
        LEFT JOIN instructors i ON ci.instructor_id = i.id
        LEFT JOIN monitored_courses mc ON c.courseCode = mc.courseCode 
            AND c.section = mc.section AND mc.username = ?
        GROUP BY c.id
        ORDER BY c.courseCode
    """, (session['username'],))
    
    courses = cursor.fetchall()
    conn.close()
    
    # Group courses by courseCode
    grouped_courses = {}
    for course in courses:
        code = course['courseCode']
        if code not in grouped_courses:
            grouped_courses[code] = []
        grouped_courses[code].append(dict(course))
    
    return render_template('view_courses.html', grouped_courses=grouped_courses)

@app.route('/toggle_monitor', methods=['POST'])
def toggle_monitor():
    """Toggle monitoring status for a course section"""
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        # Extract and validate parameters
        data = request.json
        if not all(k in data for k in ['courseCode', 'section', 'monitor']):
            return jsonify({'error': 'Missing required parameters'}), 400
            
        username = session['username']
        course_code = data['courseCode']
        section = data['section']
        monitor = data['monitor']
        year = data.get('year')
        term = data.get('term')
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if monitor:
            # Validate year and term when starting to monitor
            if not year or not term or year == 'null' or term == 'null':
                return jsonify({
                    'success': False,
                    'error': 'Year and term are required when monitoring a course'
                }), 400
            
            # Check if already monitoring
            cursor.execute("""
                SELECT id FROM monitored_courses
                WHERE username = ? AND courseCode = ? AND section = ?
            """, (username, course_code, section))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing monitoring
                cursor.execute("""
                    UPDATE monitored_courses
                    SET year = ?, term = ?
                    WHERE username = ? AND courseCode = ? AND section = ?
                """, (year, term, username, course_code, section))
            else:
                # Add new monitoring
                cursor.execute("""
                    INSERT INTO monitored_courses (username, courseCode, section, year, term)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, course_code, section, year, term))
            
            message = f'Started monitoring {course_code} section {section} for {term} {year}'
        else:
            # Remove monitoring
            cursor.execute("""
                DELETE FROM monitored_courses
                WHERE username = ? AND courseCode = ? AND section = ?
            """, (username, course_code, section))
            message = f'Stopped monitoring {course_code} section {section}'
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': message,
            'year': year if monitor else None,
            'term': term if monitor else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sync_course', methods=['POST'])
def sync_course():
    """Sync a course with the latest data"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please log in first'})
    
    try:
        # Extract request parameters
        data = request.json
        course_code = data.get('courseCode')
        section = data.get('section')
        sync_all = data.get('syncAll', False)
        year = data.get('year')
        term = data.get('term')
        
        if not course_code or not year or not term:
            return jsonify({'success': False, 'error': 'Course details are incomplete'})
        
        # Get subject code and course number
        subject = ''.join(filter(str.isalpha, course_code))
        course_num = ''.join(filter(str.isdigit, course_code))
        
        # Get user credentials
        username = session['username']
        
        # Keep the clear_auth_state call for backward compatibility
        clear_auth_state(username)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fsu_password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})
        
        # Decrypt password and fetch course data
        decrypted_password = cipher.decrypt(user['fsu_password'])
        data = scraper.fetch_course_data(year, term, subject, course_num, username, decrypted_password)
        
        if not data:
            return jsonify({'success': False, 'error': 'Failed to fetch course data'})
        
        # Process the data
        scraper.process_courses(data, year, term)
        
        # Return appropriate response
        if sync_all or not section:
            return jsonify({
                'success': True, 
                'message': f'All sections of {course_code} synced successfully'
            })
        
        return jsonify({
            'success': True, 
            'message': f'Course {course_code} section {section} synced successfully'
        })
        
    except Exception as e:
        print(f"Error syncing course: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete_course', methods=['POST'])
def delete_course():
    """Delete a course or course section from the database"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please log in first'})
    
    try:
        data = request.json
        course_code = data.get('courseCode')
        section = data.get('section')
        delete_all = data.get('deleteAll', False)
        
        if not course_code:
            return jsonify({'success': False, 'error': 'Course code is required'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if delete_all or not section:
            # Delete entire course (all sections)
            cursor.execute("SELECT id FROM courses WHERE courseCode = ?", (course_code,))
            course_ids = [row['id'] for row in cursor.fetchall()]
            
            if not course_ids:
                conn.close()
                return jsonify({'success': False, 'error': 'Course not found'})
            
            # Clean up related records
            cursor.executemany("DELETE FROM course_instructors WHERE course_id = ?", [(id,) for id in course_ids])
            cursor.execute("DELETE FROM monitored_courses WHERE courseCode = ?", (course_code,))
            cursor.execute("DELETE FROM schedule_courses WHERE courseCode = ?", (course_code,))
            
            # Delete the course
            cursor.execute("DELETE FROM courses WHERE courseCode = ?", (course_code,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True, 
                'message': f'Course {course_code} deleted successfully ({deleted_count} sections)',
                'deletedCount': deleted_count
            })
        else:
            # Delete specific section
            cursor.execute("SELECT id FROM courses WHERE courseCode = ? AND section = ?", (course_code, section))
            course = cursor.fetchone()
            
            if not course:
                conn.close()
                return jsonify({'success': False, 'error': 'Course not found'})
            
            course_id = course['id']
            
            # Clean up related records
            cursor.execute("DELETE FROM course_instructors WHERE course_id = ?", (course_id,))
            cursor.execute("DELETE FROM monitored_courses WHERE courseCode = ? AND section = ?", (course_code, section))
            cursor.execute("DELETE FROM schedule_courses WHERE courseCode = ? AND section = ?", (course_code, section))
            
            # Delete the course
            cursor.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': f'Course {course_code} section {section} deleted successfully'})
        
    except Exception as e:
        print(f"Error deleting course: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Schedule management routes
@app.route('/schedule_generator')
def schedule_generator():
    """Show the schedule generator page"""
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Get list of available courses
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT courseCode FROM courses ORDER BY courseCode")
    course_codes = [row['courseCode'] for row in cursor.fetchall()]
    conn.close()
    
    return render_template('schedule_generator.html', available_courses=course_codes)

@app.route('/generate_schedule', methods=['POST'])
def generate_schedule():
    """Generate schedules based on user constraints"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please log in first'})
    
    try:
        # Extract parameters
        earliest_time = request.form.get('earliest_time', '0800')
        latest_time = request.form.get('latest_time', '1700')
        preferred_days = request.form.getlist('preferred_days')
        required_courses = request.form.getlist('required_courses')
        optional_courses = request.form.getlist('optional_courses')
        max_courses = int(request.form.get('max_courses', 4))
        term = request.form.get('term', '2025 Fall')
        prioritize_gaps = 'prioritize_gaps' in request.form

        # Validate input
        if not required_courses and not optional_courses:
            return jsonify({
                'success': False,
                'error': 'Please select at least one required or optional course'
            })
        
        # Split term into year and semester
        term_parts = term.split(' ')
        year = term_parts[0]
        semester = term_parts[1]
        
        # Format preferred days
        preferred_days_str = ''.join(sorted(preferred_days))
        
        # Generate schedules
        schedules = generate_optimal_schedules(
            required_courses=required_courses,
            optional_courses=optional_courses,
            earliest_time=earliest_time,
            latest_time=latest_time,
            preferred_days=preferred_days_str,
            max_courses=max_courses,
            year=year,
            term=semester,
            prioritize_gaps=prioritize_gaps,
            username=session['username']
        )
        
        return jsonify({
            'success': True,
            'schedules': schedules if schedules else []
        })
        
    except Exception as e:
        print(f"Schedule generation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"Error generating schedule: {str(e)}"
        })

@app.route('/save_schedule', methods=['POST'])
def save_schedule():
    """Save a generated schedule"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please log in first'})
    
    try:
        data = request.json
        schedule_courses = data.get('courses', [])
        
        if not schedule_courses:
            return jsonify({'success': False, 'error': 'No courses in schedule'})
        
        username = session['username']
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create the schedule
        cursor.execute("""
            INSERT INTO saved_schedules (username, name, created_at)
            VALUES (?, ?, datetime('now'))
        """, (username, f"Schedule {data.get('schedule_id', 0) + 1}"))
        
        schedule_id = cursor.lastrowid
        
        # Add courses to the schedule
        for course in schedule_courses:
            cursor.execute("""
                INSERT INTO schedule_courses (schedule_id, courseCode, section)
                VALUES (?, ?, ?)
            """, (schedule_id, course['courseCode'], course['section']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Save schedule error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"Error saving schedule: {str(e)}"
        })

@app.route('/saved_schedules')
def saved_schedules():
    """View saved schedules"""
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all saved schedules
    cursor.execute("""
        SELECT id, name, created_at 
        FROM saved_schedules 
        WHERE username = ? 
        ORDER BY created_at DESC
    """, (username,))
    schedules = cursor.fetchall()
    
    # Get courses for each schedule
    for i, schedule in enumerate(schedules):
        schedule_id = schedule['id']
        cursor.execute("""
            SELECT sc.courseCode, sc.section, c.seatsCapacity, c.seatsAvailable, 
                   c.days, c.startTime, c.endTime, c.location, c.year, c.term,
                   (SELECT COUNT(*) FROM monitored_courses mc 
                    WHERE mc.username = ? AND mc.courseCode = sc.courseCode AND mc.section = sc.section) AS is_monitored
            FROM schedule_courses sc
            LEFT JOIN courses c ON sc.courseCode = c.courseCode AND sc.section = c.section
            WHERE sc.schedule_id = ?
        """, (username, schedule_id))
        courses = cursor.fetchall()
        schedules[i] = dict(schedules[i])
        schedules[i]['courses'] = [dict(course) for course in courses]
        
    conn.close()
    
    return render_template('saved_schedules.html', schedules=schedules)

@app.route('/delete_schedule', methods=['POST'])
def delete_schedule():
    """Delete a saved schedule"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please log in first'})
    
    try:
        username = session['username']
        schedule_id = request.json.get('schedule_id')
        
        if not schedule_id:
            return jsonify({'success': False, 'error': 'No schedule specified'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify ownership
        cursor.execute("""
            SELECT id FROM saved_schedules
            WHERE id = ? AND username = ?
        """, (schedule_id, username))
        
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Schedule not found or not authorized'})
        
        # Delete the schedule
        cursor.execute("DELETE FROM schedule_courses WHERE schedule_id = ?", (schedule_id,))
        cursor.execute("DELETE FROM saved_schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error deleting schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/monitor_schedule_courses', methods=['POST'])
def monitor_schedule_courses():
    """Monitor selected courses from a saved schedule"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please log in first'})
    
    try:
        username = session['username']
        schedule_id = request.json.get('schedule_id')
        course_selections = request.json.get('courses', [])
        
        if not schedule_id:
            return jsonify({'success': False, 'error': 'No schedule specified'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify ownership
        cursor.execute("""
            SELECT id FROM saved_schedules
            WHERE id = ? AND username = ?
        """, (schedule_id, username))
        
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Schedule not found or not authorized'})
        
        # Process each course selection
        monitor_results = []
        for selection in course_selections:
            course_code = selection.get('courseCode')
            section = selection.get('section')
            monitor = selection.get('monitor', True)
            
            if not course_code or not section:
                continue
            
            # Get course year and term
            cursor.execute("""
                SELECT c.year, c.term
                FROM courses c
                WHERE c.courseCode = ? AND c.section = ?
            """, (course_code, section))
            
            course_details = cursor.fetchone()
            if not course_details:
                monitor_results.append({
                    'courseCode': course_code, 
                    'section': section,
                    'success': False,
                    'error': 'Course details not found'
                })
                continue
            
            year = course_details['year']
            term = course_details['term']
            
            if monitor:
                # Check if already monitoring
                cursor.execute("""
                    SELECT id FROM monitored_courses
                    WHERE username = ? AND courseCode = ? AND section = ?
                """, (username, course_code, section))
                
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute("""
                        UPDATE monitored_courses
                        SET year = ?, term = ?
                        WHERE id = ?
                    """, (year, term, existing['id']))
                    status = 'updated'
                else:
                    cursor.execute("""
                        INSERT INTO monitored_courses (username, courseCode, section, year, term)
                        VALUES (?, ?, ?, ?, ?)
                    """, (username, course_code, section, year, term))
                    status = 'added'
            else:
                cursor.execute("""
                    DELETE FROM monitored_courses
                    WHERE username = ? AND courseCode = ? AND section = ?
                """, (username, course_code, section))
                status = 'removed'
            
            monitor_results.append({
                'courseCode': course_code, 
                'section': section,
                'success': True,
                'status': status
            })
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': monitor_results
        })
        
    except Exception as e:
        print(f"Error updating schedule monitoring: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Main application entry point
if __name__ == '__main__':
    # Initialize database
    init_db.init_db()
    
    # Add job and start scheduler
    init_scheduler_job()
    scheduler.start()
    print("Scheduler started with check_monitored_courses task running every 30 seconds")
    
    # Run Flask app
    app.run(debug=True, use_reloader=False)  # Disable reloader to prevent duplicate schedulers
