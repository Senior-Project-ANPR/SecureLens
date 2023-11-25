import dataclasses
from dataclasses import dataclass

import flask_login
from flask import Flask, render_template, Response, request, redirect, url_for, json, jsonify
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

#Create 3 tables that will act together as our main database
#First is student_tbl, which holds each student's info and sets up connections to the other two databases.
#This table won't have any duplicate entries
#Primary Key: id
class student_tbl(db.Model):
    id = db.Column(db.Integer, unique=True, nullable=False, primary_key=True, default=0)
    firstName = db.Column(db.String, nullable=False, default="firstName")
    lastName = db.Column(db.String, nullable=False, default="lastName")
    checkedOut = db.Column(db.Boolean, nullable=False, default=False)
    classNumber = db.Column(db.Integer, db.ForeignKey("class_tbl.classNumber"), nullable=False)
    car = db.relationship("car_tbl", backref="student_tbl")
    classroom = db.relationship("class_tbl", backref="student_tbl")

#Second is car_tbl, which holds each car's info, as well as a reference to the students associated with the cars.
#This table will have duplicate entries for each different student associated with a car.
#Primary Key: carPlate + id
class car_tbl(db.Model):
    carPlate = db.Column(db.String, nullable=False, primary_key=True, default="na")
    carMake = db.Column(db.String)
    carModel = db.Column(db.String)
    carColor = db.Column(db.String)
    guest = db.Column(db.Boolean, nullable=False, default=False)
    id = db.Column(db.Integer, db.ForeignKey("student_tbl.id"), nullable=False, primary_key=True)

#Third is class_tbl, which holds each classroom's info.
#This table won't have any duplicate entries.
#Primary Key: classNumber
class class_tbl(db.Model):
    classNumber = db.Column(db.Integer, unique=True, nullable=False, primary_key=True, default=99999)
    grade = db.Column(db.Integer, nullable=False)
    teacher = db.Column(db.String, nullable=False)

#Create a table called user_acct that holds an id, username, and hashed password.
#This table is separate from our main database.
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
# new_user = user_acct(username="parent", password=generate_password_hash("test"))
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
    #Authorize only admin accounts
    if flask_login.current_user.accountType != "admin":
        return redirect(url_for('log_in_page'))

    return render_template('admin_view.html')
@app.route('/release', methods=["POST", "GET"])

def release():
    #Authorize only admin & teacher accounts
    if flask_login.current_user.accountType != "admin" and flask_login.current_user.accountType != "teacher":
        return redirect(url_for('log_in_page'))

    if request.method == "POST":
        input_classroom = request.form.get("classroom")
        return redirect(f'/release/{input_classroom}')

    return render_template('release.html')
@app.route('/student/<int:student_id>')
def student_info(student_id):
    #Authorize only admin & teacher accounts
    if flask_login.current_user.accountType != "admin" and flask_login.current_user.accountType != "teacher":
        return redirect(url_for('log_in_page'))

    #Query our student database for the student associated with the given id, and query the car database
    #for all cars associated with that id
    studentCars = car_tbl.query.filter_by(id=student_id).all()
    studentName = student_tbl.query.filter_by(id=student_id).first()
    #Pass those both to our html template: the list of all rows for iterating through every vehicle, and the single
    #row for name and classroom
    return render_template('student_info.html', cars=studentCars, name=studentName)

@app.route('/release/<int:classroom>')
def release_students(classroom):
    #Authorize only admin & teacher accounts
    if flask_login.current_user.accountType != "admin" and flask_login.current_user.accountType != "teacher":
        return redirect(url_for('log_in_page'))

    #Filter our student database down to only the students in the given classroom and pass that on to our
    #HTML template
    students = student_tbl.query.filter_by(classNumber=classroom).all()
    return render_template('release_students.html', students=students, classroom=classroom)

@app.route('/cameraview')
def cameraview():
    #Authorize only admin accounts
    if flask_login.current_user.accountType != "admin":
        return redirect(url_for('log_in_page'))

    return render_template('cameraview.html')

@app.route('/video_feed')
def video_feed():
    #Authorize only admin accounts
    if flask_login.current_user.accountType != "admin":
        return redirect(url_for('log_in_page'))

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
            #If they match, log in the user and take them to a landing page dependent on their account type
            login_user(user)
            if user.accountType == "admin":
                return redirect('/admin_view')
            elif user.accountType == "teacher":
                return redirect('/release')
            else:
                return redirect('/')

    return render_template('index.html')

@app.route('/checkout/<int:student_id>')
def checkout(student_id):
    # Authorize only admin & teacher accounts
    if flask_login.current_user.accountType != "admin" and flask_login.current_user.accountType != "teacher":
        return redirect(url_for('log_in_page'))

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

@app.route('/admin_view/database', methods=["GET", "POST"])
def table_view():
    #Grab all elements from our student_tbl & car_tbl and save them as arrays, where each cell is an element
    allStudents = student_tbl.query.all()
    allCars = car_tbl.query.all()
    studentList = []
    carList = []

    for student in allStudents:
        studentList.append(student.id)
        studentList.append(student.firstName)
        studentList.append(student.lastName)
        studentList.append(student.classNumber)
        studentList.append(student.checkedOut)

    for car in allCars:
        carList.append(car.carPlate)
        carList.append(car.carMake)
        carList.append(car.carModel)
        carList.append(car.carColor)
        carList.append(car.id)
        carList.append(car.guest)

    return render_template('table_view.html', students=studentList, cars=carList)

#Route to add a student to the database after submission of the add form
@app.route('/admin_view/database/add', methods=["GET", "POST"])
def table_view_addStudent():
    #Grab all the entries from the form and store them in local variables
    idIn = request.form.get("id")
    firstNameIn = request.form.get("firstName")
    lastNameIn = request.form.get("lastName")
    classNumberIn = request.form.get("classNumber")

    #debug
    print(f"{idIn}")
    print(f"{firstNameIn}")
    print(f"{lastNameIn}")
    print(f"{classNumberIn}")
    #debug

    #Format the entries received into a row for our student_tbl
    inUser = student_tbl(
        id=idIn,
        firstName=firstNameIn,
        lastName=lastNameIn,
        classNumber=classNumberIn,
        checkedOut=0,
    )

    #Add the row to the database and commit the change
    db.session.add(inUser)
    db.session.commit()

    #redirect back to the database view
    return redirect(url_for('table_view'))

@app.route('/admin_view/database/edit', methods=["GET", "POST"])
def table_view_editStudent():
    #Grab all the entries from the form and store them in local variables, as well as the original
    #id of the student we're editing
    idIn = request.form.get("id")
    ogId = request.form.get("ogId")
    firstNameIn = request.form.get("firstName")
    lastNameIn = request.form.get("lastName")
    classNumberIn = request.form.get("classNumber")
    checkedOutIn = request.form.get("checkedOut")

    #Find the student we're editing in the database and change its data to the edited info
    editRow = student_tbl.query.filter_by(id=ogId).first()

    editRow.id = idIn
    editRow.firstName = firstNameIn
    editRow.lastName = lastNameIn
    editRow.classNumber = classNumberIn
    #Since HTML doesn't return a boolean for checkboxes, we check if the incoming data exists or not.
    #If it does, that means the checkbox was checked
    if checkedOutIn:
        editRow.checkedOut = 1
    else:
        editRow.checkedOut = 0

    #Commit our changes and go back to database view
    db.session.commit()

    return redirect(url_for('table_view'))

@app.route('/admin_view/database/remove', methods=["GET", "POST"])
def table_view_removeStudent():

    #Get the id of the currently selected student
    idIn = request.form.get("removeButtonId")

    #If the id is null (the default value for when no student is selected), redirect to the error page, otherwise
    #delete the student from the db, commit the changes, and reload the page
    if (idIn == "null"):
        return redirect(url_for('table_view_error'))
    else:
        student_tbl.query.filter_by(id=idIn).delete()

    db.session.commit()
    return redirect(url_for('table_view'))

@app.route('/admin_view/database/error', methods=["GET"])
def table_view_error():

    return redirect(url_for('table_view'))

if __name__ == '__main__':
    app.run(debug=True)