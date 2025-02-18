from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import init_db
import scraper
from encryption import cipher

app = Flask(__name__)
app.secret_key = 'GONOLES!'

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

@app.route('/view_courses')
def view_courses():
    if 'username' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    conn.close()
    return render_template('view_courses.html', courses=courses)

if __name__ == '__main__':
    init_db.init_db()
    app.run(debug=True)
