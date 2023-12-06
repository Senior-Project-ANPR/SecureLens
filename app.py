from flask import Flask, render_template, Response, request, redirect, url_for
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify
from flask_restful import Resource, Api
import cv2
from ultralytics import YOLO
import easyocr
import re

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


desired_width = 854
desired_height = 480
IGNORED_WORD = "TEXAS"

reader = easyocr.Reader(['en'])
cap = cv2.VideoCapture(0)
model_path = 'best.pt'
model = YOLO(model_path)
threshold = 0.5

detected_plates = []

def generate_plates_improved():
    while True:
        ret, image = cap.read()

        if not ret:
            break

        image = cv2.resize(image, (desired_width, desired_height))
        results = model(image)[0]

        for result in results.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = result
            class_name = results.names[int(class_id)]

            if score > threshold:
                cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 4)

                if class_name == 'plate':
                    plate_image = image[int(y1):int(y2), int(x1):int(x2)]
                    gray_plate = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
                    ocr_results = reader.readtext(gray_plate)

                    detected_text = ' '.join([item[1] for item in ocr_results]).strip().upper()
                    match = re.search(r'\b\w{3}-\w{4}\b', detected_text)
                    formatted_plate = match.group() if match else "Not Found"

                    if formatted_plate != "Not Found" and formatted_plate not in detected_plates:
                        detected_plates.append(formatted_plate)

                    if formatted_plate != "Not Found":
                        cv2.putText(image, "License Plate: " + formatted_plate, (int(x1), int(y1 - 40)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    with app.app_context():
                        if formatted_plate != "Not Found":
                            db_formatted_plate = formatted_plate.replace('-', '')
                            print(f"{db_formatted_plate}")
                            tempStudent = car_tbl.query.filter_by(carPlate=db_formatted_plate).all()
                            if tempStudent:
                                for record in tempStudent:
                                    selection = student_tbl.query.filter_by(id=record.id).first()
                                    tempFirstName = selection.firstName
                                    tempLastName = selection.lastName
                                    tempClassroom = selection.classNumber
                                    print(
                                        f"License Plate Recognized. Student: {tempFirstName} {tempLastName}, Classroom: {tempClassroom}")
                                if formatted_plate not in detected_plates:
                                    detected_plates.append(formatted_plate)
                                print(f"{detected_plates}")

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
@login_required
def admin_view():
    return render_template('admin_view.html')

@app.route('/teacher_view')
@login_required
def teacher_view():
    return render_template('teacher_view.html')


@app.route('/release', methods=["POST", "GET"])
@login_required
def release():
    if request.method == "POST":
        input_classroom = request.form.get("classroom")
        return redirect(f'/release/{input_classroom}')

    return render_template('release.html')

@app.route('/student/<int:student_id>')
@login_required
def student_info(student_id):
    #Query our student database for the student associated with the given id, and query the car database
    #for all cars associated with that id
    studentCars = car_tbl.query.filter_by(id=student_id).all()
    studentName = student_tbl.query.filter_by(id=student_id).first()
    #Pass those both to our html template: the list of all rows for iterating through every vehicle, and the single
    #row for name and classroom
    return render_template('student_info.html', cars=studentCars, name=studentName)

@app.route('/release/<int:classroom>')
@login_required
def release_students(classroom):
    #Filter our student database down to only the students in the given classroom and pass that on to our
    #HTML template
    students = student_tbl.query.filter_by(classNumber=classroom).all()
    return render_template('release_students.html', students=students, classroom=classroom)

@app.route('/cameraview')
@login_required
def cameraview():
    return render_template('cameraview.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_plates_improved(), mimetype='multipart/x-mixed-replace; boundary=frame')

#Our main landing page/login page. We will need to receive and send text from the page,
#so we set up GET and POST, so we can use them
@app.route('/', methods=["GET", "POST"])
def log_in_page():
    if request.method == "POST":
        input_username = request.form.get("Username")
        input_password_hashed = request.form.get("Password")

        user = user_acct.query.filter_by(username=input_username).first()

        if not user:
            return redirect('/')

        # Compare the hashed password with the one stored in the database
        if check_password_hash(user.password, input_password_hashed):
            # Successfully authenticated
            login_user(user)
            return redirect('/admin_view')

    return render_template('index.html')



@app.route('/checkout/<int:student_id>')
@login_required
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
    return redirect(url_for('table_view', classroom=classroom))

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
@app.route('/admin_view/database/add/student', methods=["GET", "POST"])
def table_view_addStudent():
    #Grab all the entries from the form and store them in local variables
    idIn = request.form.get("id")
    firstNameIn = request.form.get("firstName").capitalize()
    lastNameIn = request.form.get("lastName").capitalize()
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

@app.route('/admin_view/database/edit/student', methods=["GET", "POST"])
def table_view_editStudent():
    #Grab all the entries from the form and store them in local variables, as well as the original
    #id of the student we're editing
    idIn = request.form.get("id")
    ogId = request.form.get("ogId")
    firstNameIn = request.form.get("firstName").capitalize()
    lastNameIn = request.form.get("lastName").capitalize()
    classNumberIn = request.form.get("classNumber")
    checkedOutIn = request.form.get("checkedOut")


    #Find the student we're editing in the database and change its data to the edited info
    editRow = student_tbl.query.filter_by(id=ogId).first()

    editRow.id = idIn
    editRow.firstName = firstNameIn
    editRow.lastName = lastNameIn
    editRow.classNumber = classNumberIn

    #Convert our dropdown selection from a string into an actual boolean
    if checkedOutIn == "true":
        editRow.checkedOut = 1
    else:
        editRow.checkedOut = 0

    #Commit our changes and go back to database view
    db.session.commit()

    return redirect(url_for('table_view'))

@app.route('/admin_view/database/remove/student', methods=["GET", "POST"])
def table_view_removeStudent():
    #Get the id of the currently selected student
    idIn = request.form.get("studentRemoveId")

    #If the id is null (the default value for when no student is selected), redirect to the error page, otherwise
    #delete the student from the db, commit the changes, and reload the page
    if (idIn == "null"):
        return redirect(url_for('table_view_error'))
    else:
        student_tbl.query.filter_by(id=idIn).delete()

    db.session.commit()
    return redirect(url_for('table_view'))

@app.route('/admin_view/database/add/car', methods=["GET", "POST"])
def table_view_addCar():
    #Grab all the entries from the form and store them in local variables, as well as the selected
    #student's ID so we can connect the car to them
    plateIn = request.form.get("carPlate").upper()
    idIn = request.form.get("id")
    makeIn = request.form.get("carMake").capitalize()
    modelIn = request.form.get("carModel").capitalize()
    colorIn = request.form.get("carColor").capitalize()
    guestIn = request.form.get("guest")


    # Since HTML doesn't return a boolean for checkboxes, we check if the incoming data exists or not.
    # If it does, that means the checkbox was checked
    if guestIn:
        guestIn = 1
    else:
        guestIn = 0

    #debug
    print(f"{idIn}")
    print(f"{plateIn}")
    print(f"{makeIn}")
    print(f"{modelIn}")
    print(f"{colorIn}")
    print(f"{guestIn}")
    #debug

    #Format the entries received into a row for our car_tbl
    inCar = car_tbl(
        carPlate = plateIn,
        carMake = makeIn,
        carModel = modelIn,
        carColor = colorIn,
        id = idIn,
        guest = guestIn
    )

    #Add the row to the database and commit the change
    db.session.add(inCar)
    db.session.commit()

    #redirect back to the database view
    return redirect(url_for('table_view'))

@app.route('/admin_view/database/edit/car', methods=["GET", "POST"])
def table_view_editCar():
    #Grab all the entries from the form and store them in local variables, as well as the car's original plate
    #so we don't try to query the edited value
    plateIn = request.form.get("carPlate").upper()
    ogPlate = request.form.get("ogPlate")
    idIn = request.form.get("id")
    makeIn = request.form.get("carMake").capitalize()
    modelIn = request.form.get("carModel").capitalize()
    colorIn = request.form.get("carColor").capitalize()
    guestIn = request.form.get("guest")


    #Find the car we're editing in the database and change its data to the edited info
    editRow = car_tbl.query.filter_by(carPlate=ogPlate, id=idIn).first()
    print(f"{ogPlate}")
    print(f"{idIn}")
    print(f"{editRow}")

    editRow.carPlate = plateIn
    editRow.carMake = makeIn
    editRow.carModel = modelIn
    editRow.carColor = colorIn
    editRow.guest = guestIn

    #Convert our dropdown selection from a string into an actual boolean
    if guestIn == "true":
        editRow.guest = 1
    else:
        editRow.guest = 0

    #Commit our changes and go back to database view
    db.session.commit()

    return redirect(url_for('table_view'))

@app.route('/admin_view/database/remove/car', methods=["GET", "POST"])
def table_view_removeCar():
    #Get the plate number and associated student ID of the currently selected car
    plateIn = request.form.get("carRemovePlate")
    idIn = request.form.get("carRemoveId")

    #If the id is null (the default value for when no student is selected), redirect to the error page, otherwise
    #delete the student from the db, commit the changes, and reload the page
    if (idIn == "null" or plateIn == "null"):
        return redirect(url_for('table_view_error'))
    else:
        car_tbl.query.filter_by(carPlate=plateIn, id=idIn).delete()

    #Commit our changes and go back to database view
    db.session.commit()
    return redirect(url_for('table_view'))

@app.route('/admin_view/database/transfer', methods=["GET", "POST"])
def table_view_changeCarId():
    #Get the plate number, original student id, and new student id of the car
    plateIn = request.form.get("changeCarPlate")
    idIn = request.form.get("changeCarId")
    ogId = request.form.get("changeCarOgId")

    print(f"{plateIn}, {idIn}, {ogId}")

    editRow = car_tbl.query.filter_by(carPlate=plateIn, id=ogId).first()

    #Likewise if the query fails, return the error page
    if not editRow:
        return redirect(url_for('table_view_error'))

    editRow.id = idIn

    # Commit our changes and go back to database view
    db.session.commit()
    return redirect(url_for('table_view'))

@app.route('/admin_view/database/error', methods=["GET"])
def table_view_error():
    return redirect(url_for('table_view'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

api = Api(app)

class StudentSearchAPI(Resource):
    def post(self):
        data = request.get_json()
        student_name = data.get('student_name')
        teacher_name = data.get('teacher_name')
        room_number = data.get('room_number')

        students = student_tbl.query.filter_by(firstName=student_name, classroom=room_number).all()

        serialized_students = [{
            'id': student.id,
            'firstName': student.firstName,
            'lastName': student.lastName,
            'classroom': student.classroom,
            'carMake': student.carMake,
            'carModel': student.carModel,
            'carColor': student.carColor,
            'carPlate': student.carPlate,
            'guest': student.guest,
            'checkedOut': student.checkedOut
        } for student in students]

        return jsonify(serialized_students)

class StudentCheckoutAPI(Resource):
    def post(self, student_id):
        student=student_tbl.query.filter_by(id=student_id).first()
        if student is None:
            return jsonify({'error' : 'Not found'}), 404

        student.checkedOut = True
        db.session.commit()

        return jsonify({'message' : 'Successfully checked out the student.'})

api.add_resource(StudentSearchAPI, '/api/search')
api.add_resource(StudentCheckoutAPI, '/api/checkout/<int:student_id>')


if __name__ == '__main__':
    app.run(debug=True)