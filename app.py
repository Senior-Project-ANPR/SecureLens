from flask import Flask, render_template, Response
import cv2
import pytesseract
import os
import sqlite3
from flask import render_template, redirect, url_for, flash



# Connect to the database
conn = sqlite3.connect('student.db')
c = conn.cursor()

# Drop the 'students' table if it exists
c.execute('DROP TABLE IF EXISTS students')

# Create the 'students' table with the updated schema
c.execute('''CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    parents TEXT,
    vehicles TEXT,
    grade INTEGER,
    teacher TEXT,
    classroom INTEGER,
    license_plate TEXT,
    released INTEGER DEFAULT 0
)''')

# Sample student data
sample_students = [
    ('Jon Doe', 'Jack Doe, Jane Doe', 'Yellow Jeep Wrangler', 3, 'Ms. Garza', 28, '3SAM123'),
    ('Alice Smith', 'Bob Smith, Carol Smith', 'Red Toyota Camry', 4, 'Mr. Johnson', 28, 'ABC456'),
    ('Ella Johnson', 'David Johnson, Sophia Johnson', 'Blue Honda Accord', 2, 'Ms. Davis', 28, 'XYZ789'),
    # Add more students for testing here
]

# Insert sample students into the database
for student_data in sample_students:
    c.execute('''INSERT INTO students (name, parents, vehicles, grade, teacher, classroom, license_plate)
                  VALUES (?, ?, ?, ?, ?, ?, ?)''', student_data)

# Commit changes and close the connection
conn.commit()
conn.close()

app = Flask(__name__)

if not os.path.exists('captured_images'):
    os.makedirs('captured_images')

cap = cv2.VideoCapture(0)

# Define min and max dimensions for license plates
min_width = 80
min_height = 40
max_width = 400
max_height = 200

# Define the width and height frame of the cameraview
desired_width = 854
desired_height = 480

def generate_frames():
    while True:
        ret, frame = cap.read()

        # Resize the frame to the desired width and height
        frame = cv2.resize(frame, (desired_width, desired_height))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresholded = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > min_width and h > min_height and w < max_width and h < max_height:
                plate_region = thresholded[y:y + h, x:x + w]

                plate_text = pytesseract.image_to_string(plate_region,
                                                         config='--psm 12 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 0), 2)
                cv2.putText(frame, 'License Plate: ' + plate_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 0, 0), 2)

                # Check if the recognized license plate is in the database and not released
                conn = sqlite3.connect('student.db')
                c = conn.cursor()
                c.execute('SELECT * FROM students WHERE license_plate = ? AND released = 0', (plate_text,))
                student = c.fetchone()

                if student:
                    print(f"License Plate Recognized. Student: {student[1]}, Classroom: {student[6]}")
                    # Mark the student as released in the database
                    c.execute('UPDATE students SET released = 1 WHERE id = ?', (student[0],))
                    conn.commit()
                conn.close()

        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/student/<int:student_id>')
def student_info(student_id):
    conn = sqlite3.connect('student.db')
    c = conn.cursor()

    # Retrieve student information by ID from the database
    c.execute('SELECT * FROM students WHERE id = ?', (student_id,))
    student = c.fetchone()

    conn.close()

    return render_template('student_info.html', student=student)

@app.route('/release/<int:classroom>')
def release_students(classroom):
    conn = sqlite3.connect('student.db')
    c = conn.cursor()

    c.execute('SELECT * FROM students WHERE classroom = ? AND released = 1', (classroom,))
    students = c.fetchall()

    conn.close()

    return render_template('release_students.html', students=students, classroom=classroom)
@app.route('/cameraview')
def cameraview():
    return render_template('cameraview.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def hello_world():
    return render_template('index.html')

# Import the authentication blueprint if you're using one
# from .auth import auth_bp
#auth_bp = Blueprint('auth', __name__)
#app.register_blueprint(recognition_bp)

#@app.route('/register', methods=['GET', 'POST'])
#def register():
#    form = RegistrationForm()
#    if form.validate_on_submit():
#        # Process the registration form data and create a new user
#        flash('Registration successful. You can now log in.', 'success')
#        return redirect(url_for('login'))
#    return render_template('register.html', form=form)

#@app.route('/login', methods=['GET', 'POST'])
#def login():
#    form = LoginForm()
#    if form.validate_on_submit():
#        # Process the login form data and authenticate the user
#        flash('Login successful.', 'success')
#        return redirect(url_for('dashboard'))  # Redirect to the dashboard or another page
#    return render_template('login.html', form=form)


if __name__ == '__main__':
    app.run(debug=True)
