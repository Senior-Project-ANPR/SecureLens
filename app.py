from flask import Flask, render_template, Response, request, redirect
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user
from werkzeug.security import generate_password_hash, check_password_hash
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

#Specify which database for the app to connect to and create a secret key
#NOTE: Once we change the student database to SQLAlchemy we may have to use binds, so we can have 2 dbs
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite"
app.config["SECRET_KEY"] = "xg7zbb5iyvcp"

#Init SQLAlchemy
db = SQLAlchemy()
db.init_app(app)

#Create the login database schema
with app.app_context():
    db.create_all()

#Init LoginManager from Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

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

#Create a class for our login db called user_acct that holds an id, username, and hashed password
class user_acct(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)

#Create a user loader that takes the id of the user and returns the user_acct
@login_manager.user_loader
def load_user(user_id):
    return user_acct.query.get(user_id)

#Uncomment to add a test account to the login database
#We use generate_password_hash to avoid saving plaintext passwords in our database
#new_user = user_acct(username="test", password=generate_password_hash("test"))
#with app.app_context():
#    db.session.add(new_user)
#    db.session.commit()

#Uncomment to delete the test account from the login database
# with app.app_context():
#     user_acct.query.filter_by(username="test").delete()
#     db.session.commit()

@app.route('/admin_view')
def admin_view():
    return render_template('admin_view.html')
@app.route('/release', methods=["POST", "GET"])
def release():
    if request.method == "POST":
        input_classroom = request.form.get("classroom")
        return redirect(f'/release/{input_classroom}')

    return render_template('release.html')
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

#Our main landing page/login page. We will need to receive and send text from the page,
#so we set up GET and POST, so we can use them
@app.route('/', methods=["GET", "POST"])
def log_in_page():
    #If info is POSTed from the webpage...
    if request.method == "POST":
        #Save the Username and Password our user input
        input_username = request.form.get("Username")
        input_password = request.form.get("Password")
        #Search the database for a user_acct with a username matching the input username
        user = user_acct.query.filter_by(username=input_username).first()
        #If no such user is found, redirect back to the landing page
        if not user:
            return redirect('/')
        #Otherwise, if we did find a user with that username, hash the password input and compare it with
        #the already hashed value in our database
        if check_password_hash(user.password, input_password):
            #If they match, log in the user and take them to the camera view page
            login_user(user)
            print("Database Password: ", user.password)
            return redirect('/cameraview')
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)