from flask import Flask, render_template, Response
from flask_bootstrap import Bootstrap
import cv2
import pytesseract
import os
import sqlite3


conn = sqlite3.connect('student.db')
c = conn.cursor()

# JUST FOR TESTING
c.execute('DROP TABLE IF EXISTS students')

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

# JUST FOR TESTING
sample_students = [
    ('Jon Doe', 'Jack Doe, Jane Doe', 'Yellow Jeep Wrangler', 3, 'Ms. Garza', 28, '3SAM123'),
    ('Alice Smith', 'Bob Smith, Carol Smith', 'Red Toyota Camry', 4, 'Mr. Johnson', 28, 'ABC456K'),
    ('Ella Johnson', 'David Johnson, Sophia Johnson', 'Blue Honda Accord', 2, 'Ms. Davis', 28, 'XYZ789P'),
    # Add more students for testing here
]

for student_data in sample_students:
    c.execute('''INSERT INTO students (name, parents, vehicles, grade, teacher, classroom, license_plate)
                  VALUES (?, ?, ?, ?, ?, ?, ?)''', student_data)

conn.commit()
conn.close()


app = Flask(__name__)
boostrap = Bootstrap(app)

if not os.path.exists('captured_images'):
    os.makedirs('captured_images')

cap = cv2.VideoCapture(0)

desired_width = 854
desired_height = 480
IGNORED_WORD = "TEXAS"


def generate_plates_improved():
    while True:
        ret, image = cap.read()

        if not ret:
            break

        image = cv2.resize(image, (desired_width, desired_height))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edges = cv2.Canny(gray, 170, 200)
        cnts, new = cv2.findContours(edges.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:30]
        NumberPlateCount = None

        count = 0
        name = 1
        x = None
        y = None
        for i in cnts:
            perimeter = cv2.arcLength(i, True)
            approx = cv2.approxPolyDP(i, 0.02 * perimeter, True)
            if len(approx) == 4:
                NumberPlateCount = approx
                x, y, w, h = cv2.boundingRect(i)
                crp_img = image[y:y + h, x:x + w]
                cv2.imwrite(str(name) + '.png', crp_img)
                name += 1

                break

        if NumberPlateCount is not None:
            cv2.drawContours(image, [NumberPlateCount], -1, (0, 255, 0), 3)

        crp_img_loc = '1.png'
        text = pytesseract.image_to_string(crp_img_loc,
                                           config='--psm 12 -c tessedit_char_whitelist='
                                                  'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        text = text.replace(IGNORED_WORD, "").strip()
        text = text.strip()

        print("Number is : ", text)

        if x is not None and y is not None:
            cv2.putText(image, "License Plate: " + text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        conn = sqlite3.connect('student.db')
        c = conn.cursor()
        c.execute('SELECT * FROM students WHERE license_plate = ? AND released = 0', (text,))
        student = c.fetchone()

        if student:
            print(f"License Plate Recognized. Student: {student[1]}, Classroom: {student[6]}")
            # Mark the student as released in the database
            c.execute('UPDATE students SET released = 1 WHERE id = ?', (student[0],))
            conn.commit()
        conn.close()

        _, buffer = cv2.imencode('.jpg', image)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
@app.route('/student/<int:student_id>')
def student_info(student_id):
    conn = sqlite3.connect('student.db')
    c = conn.cursor()

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
    return Response(generate_plates_improved(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def log_in_page():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)