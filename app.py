from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_socketio import SocketIO  # Change this import
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import init_db
import scraper
from encryption import cipher
import threading
import time

app = Flask(__name__)
app.secret_key = 'GONOLES!'
socketio = SocketIO(app)  # Initialize Flask-SocketIO

def get_db_connection():
    conn = sqlite3.connect('fsu_courses.db')
    conn.row_factory = sqlite3.Row
    return conn

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
    return render_template('dashboard.html')

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if 'username' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        year = request.form['year']
        term = request.form['term']
        subject = request.form['subject']
        course = request.form['course']
        username = session['username']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fsu_password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user:
            decrypted_password = cipher.decrypt(user['fsu_password'])
            try:
                cookies = scraper.get_cookie(username, decrypted_password, headless=True)
                data = scraper.fetch_course_data(year, term, subject, course, cookies)
                scraper.process_courses(data)
                flash('Course data processed successfully!', 'success')
            except Exception as e:
                flash(f'Error processing course: {str(e)}', 'danger')
            return redirect(url_for('dashboard'))
        else:
            flash('User not found!', 'danger')
            return redirect(url_for('dashboard'))
    return render_template('add_course.html')

@app.route('/toggle_monitor', methods=['POST'])
def toggle_monitor():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
        
    data = request.json
    username = session['username']
    course_code = data['courseCode']
    section = data['section']
    monitor = data['monitor']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if monitor:
            cursor.execute("""
                INSERT INTO monitored_courses (username, courseCode, section)
                VALUES (?, ?, ?)
            """, (username, course_code, section))
        else:
            cursor.execute("""
                DELETE FROM monitored_courses
                WHERE username = ? AND courseCode = ? AND section = ?
            """, (username, course_code, section))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/view_courses')
def view_courses():
    if 'username' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    
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

def send_notification(username, message):
    """Send notification to specific user via WebSocket."""
    socketio.emit('notification', {'message': message}, room=username)

if __name__ == '__main__':
    init_db.init_db()
    # Start monitoring thread with correct argument name
    monitor_thread = threading.Thread(
        target=scraper.check_monitored_courses,
        args=(send_notification,),
        daemon=True
    )
    monitor_thread.start()
    socketio.run(app, debug=True)  # This will now work with Flask-SocketIO

