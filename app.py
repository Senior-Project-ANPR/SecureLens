from flask import Flask, render_template, Response, request, redirect, url_for
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user
from werkzeug.security import generate_password_hash, check_password_hash
import cv2
import pytesseract
import os
import sqlite3

app = Flask(__name__)
boostrap = Bootstrap(app)

#Create our main database session for our student database and a bind (parallel session) for our account database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite"
app.config["SQLALCHEMY_BINDS"] = {
    #"accounts": "sqlite:///accounts.sqlite"
}
app.config["SECRET_KEY"] = "xg7zbb5iyvcp"

#Init SQLAlchemy
db = SQLAlchemy()
db.init_app(app)

#Create a table called student_tbl that holds all required info for our students
#Current primary key is a combo of Student ID and License Plate #
class student_tbl(db.Model):
    id = db.Column(db.Integer, unique=True, nullable=False, primary_key=True, default=0)
    firstName = db.Column(db.String, nullable=False, default="firstName")
    lastName = db.Column(db.String, nullable=False, default="lastName")
    guest = db.Column(db.Boolean, nullable=False, default=False)
    checkedOut = db.Column(db.Boolean, nullable=False, default=False)
    classNumber = db.Column(db.Integer, db.ForeignKey("class_tbl.classNumber"), nullable=False)
    car = db.relationship("car_tbl", backref="student_tbl")
    classroom = db.relationship("class_tbl", backref="student_tbl")

class car_tbl(db.Model):
    carPlate = db.Column(db.String, nullable=False, primary_key=True, default="na")
    carMake = db.Column(db.String)
    carModel = db.Column(db.String)
    carColor = db.Column(db.String)
    id = db.Column(db.Integer, db.ForeignKey("student_tbl.id"), nullable=False, primary_key=True)

class class_tbl(db.Model):
    classNumber = db.Column(db.Integer, unique=True, nullable=False, primary_key=True, default=99999)
    grade = db.Column(db.Integer, nullable=False)
    teacher = db.Column(db.String, nullable=False)

#Create a table called user_acct that holds an id, username, and hashed password
class user_acct(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    accountType = db.Column(db.String, nullable=False)

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

        #Define our app context so we can access the database
        with app.app_context():
            #set tempRecords as a table whose contents are all rows attached to the read license plate
            tempRecords = car_tbl.query.filter_by(carPlate=text).all()
            #If tempStudent is not empty, iterate through it, grab the first and last name and classroom number of
            #each row, and print them
            if tempRecords:
                for record in tempRecords:
                    studentRecord = student_tbl.query.filter_by(id=record.id).first()
                    tempFirstName = studentRecord.firstName
                    tempLastName = studentRecord.lastName
                    tempClassroom = studentRecord.classNumber
                    print(f"License Plate Recognized. Student: {tempFirstName} {tempLastName}, Classroom: {tempClassroom}")

        _, buffer = cv2.imencode('.jpg', image)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

#Create a user loader that takes the id of the user and returns the user_acct
@login_manager.user_loader
def load_user(user_id):
    return user_acct.query.get(user_id)

#Uncomment to add a test account to the login database
#We use generate_password_hash to avoid saving plaintext passwords in our database
# new_user = user_acct(username="test", password=generate_password_hash("test"))
# with app.app_context():
#     db.session.add(new_user)
#     db.session.commit()

#Uncomment to add a test account to the student database
# new_user = student_tbl(
#     id = 123456789,
#     firstName = "Test",
#     lastName = "Student",
#     classroom = 1,
#     carMake = "Nissan",
#     carModel = "Skyline GT-R R34",
#     carColor = "Blue",
#     carPlate = "ABC123")
# with app.app_context():
#     db.session.add(new_user)
#     db.session.commit()

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
    #Query our student database for the student associated with the given id, and query the car database
    #for all cars associated with that id
    studentCars = car_tbl.query.filter_by(id=student_id).all()
    studentName = student_tbl.query.filter_by(id=student_id).first()
    #Pass those both to our html template: the list of all rows for iterating through every vehicle, and the single
    #row for name and classroom
    return render_template('student_info.html', cars=studentCars, name=studentName)

@app.route('/release/<int:classroom>')
def release_students(classroom):
    #Filter our student database down to only the students in the given classroom and pass that on to our
    #HTML template
    students = student_tbl.query.filter_by(classNumber=classroom).all()
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
            return redirect('/admin_view')
    return render_template('index.html')

@app.route('/checkout/<int:student_id>')
def checkout(student_id):
    #Define the change we'll be making to the checkedOut column
    checked_out = {
        'checkedOut': True
    }

    #Filter our student database by the given id, update all rows with that id to be checked out, and commit the changes
    student = db.session.query(student_tbl).filter_by(id=student_id).update(checked_out)
    db.session.commit()

    #Get the student's classroom and redirect back to that page once we're done updating the database
    temp = student_tbl.query.filter_by(id=student_id).first()
    classroom = temp.classNumber
    return redirect(url_for('release_students', classroom=classroom))

if __name__ == '__main__':
    app.run(debug=True)