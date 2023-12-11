from operator import or_
from flask import Flask, render_template, Response, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
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
    "accounts": "sqlite:///accounts.sqlite"
}
app.config["SECRET_KEY"] = "xg7zbb5iyvcp"

#Init SQLAlchemy
db = SQLAlchemy()
db.init_app(app)

#Create a table called student_tbl that holds all required info for our students
#Current primary key is a combo of Student ID and License Plate #
class student_tbl(db.Model):
    id = db.Column(db.Integer, nullable=False, primary_key=True)
    firstName = db.Column(db.String, nullable=False)
    lastName = db.Column(db.String, nullable=False)
    classNumber = db.Column(db.Integer, nullable=False)
    #guest = db.Column(db.Boolean, nullable=False, default=False)
    checkedOut = db.Column(db.Boolean, nullable=False, default=False)

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

#Create a table called user_acct that holds an id, username, and hashed password
class user_acct(UserMixin, db.Model):
    __bind_key__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    accountType = db.Column(db.String, nullable=False)

#Create the login database schema
with app.app_context():
    db.create_all()

# Init LoginManager from Flask-Login
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
#An array that'll hold the sids for all students whose cars have been read by the camera but not checked out yet
released_students = [123456788, 348297930, 636464655, 123158132, 453968089, 474867967, 847326248, 854678567]

#Function run by our automated database maintainer.
#It resets every student's checkedOut status to false and deletes any guest cars in the database
def run_db_maintenance():
    with app.app_context():
        student_tbl.query.update({student_tbl.checkedOut: 0})
        car_tbl.query.filter_by(guest=1).delete()

        db.session.commit()

#Set the hour and minute for the db reset to the value saved in our txt file
inFile = open("schedule.txt", "r")
dbResetHour = inFile.readline()
dbResetMinute = inFile.readline()
inFile.close()

#Our automated database maintainer. Sets up a background scheduler to keep track of the time and what to run
scheduler = BackgroundScheduler()
#Add a job to our scheduler to run run_db_maintenance at the given hour and minute of every day
scheduler.add_job(
    func=run_db_maintenance,
    trigger="cron",
    id="resetScheduler",
    max_instances=1,
    hour=dbResetHour,
    minute=dbResetMinute
)
scheduler.start()

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

                    print(f"{formatted_plate}")

                    if formatted_plate != "Not Found" and formatted_plate not in detected_plates:
                        detected_plates.append(formatted_plate)
                        print(f"{detected_plates}")

                    if formatted_plate != "Not Found":
                        cv2.putText(image, "License Plate: " + formatted_plate, (int(x1), int(y1 - 40)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    with app.app_context():
                        if formatted_plate != "Not Found":
                            db_formatted_plate = formatted_plate.replace('-', '')
                            tempStudent = car_tbl.query.filter_by(carPlate=db_formatted_plate).all()
                            if tempStudent:
                                for record in tempStudent:
                                    selection = student_tbl.query.filter_by(id=record.id).first()
                                    tempFirstName = selection.firstName
                                    tempLastName = selection.lastName
                                    tempClassroom = selection.classNumber
                                    print(
                                        f"License Plate Recognized. Student: {tempFirstName} {tempLastName}, Classroom: {tempClassroom}")
                                    # Check if the student is already checked out, and if not add their id to released_students
                                    if selection.checkedOut != 1 and selection.id not in released_students:
                                        released_students.append(selection.id)
                            print(f"{released_students}")

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
#new_user = user_acct(username="admin", password=generate_password_hash("admin"), accountType="admin")
#with app.app_context():
#   db.session.add(new_user)
#   db.session.commit()

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
#with app.app_context():
#   user_acct.query.filter_by(username="admin").delete()
#   db.session.commit()


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
    #Query our student database for two things: a list of all rows associated with a certain id and a single row
    #for that id
    student = student_tbl.query.filter_by(id=student_id).all()
    studentName = student_tbl.query.filter_by(id=student_id).first()
    #Pass those both to our html template: the list of all rows for iterating through every vehicle, and the single
    #row for name and classroom
    return render_template('student_info.html', student=student, name=studentName)

@app.route('/release/<int:room_number>')
@login_required
def release_students(room_number):
    students = []
    #Filter our student database down to only the students in the given classroom whose vehicles have arrived and pass
    #that on to our HTML template
    print(f"released_students: {released_students}")
    for sid in released_students:
        if student_tbl.query.filter_by(id=sid, classNumber=room_number).first():
            students.append(student_tbl.query.filter_by(id=sid, classNumber=room_number).first())
    print(f"{students}")
    return render_template('release_students.html', students=students, room_number=room_number)

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
    #If info is POSTed from the webpage...
    if request.method == "POST":
        #Save the Username and Password our user input
        input_username = request.form.get("Username")
        input_password = request.form.get("Password")

        user = user_acct.query.filter_by(username=input_username).first()

        if not user or not check_password_hash(user.password, input_password):
            if request.headers.get('User-Agent').startswith('Google'):  # Check if the request is from chrome
                return redirect('/')
            else:
                return jsonify(success=False, message="Invalid username or password")

        # Compare the hashed password with the one stored in the database
        if check_password_hash(user.password, input_password):
        # Successfully authenticated
                login_user(user)
                if request.headers.get('User-Agent').startswith('Mozilla'):
                # This is a web browser
                    if user.accountType == 'admin':
                        return redirect(url_for('admin_view'))
                    elif user.accountType == 'teacher':
                        return redirect(url_for('teacher_view'))
                else:
                    # This is likely the mobile app
                    if user.accountType == 'admin':
                        return jsonify(success=True, message="Login Successful", redirect_url='/admin_view')
                    elif user.accountType == 'teacher':
                        return jsonify(success=True, message="Login Successful", redirect_url='/teacher_view')

    return render_template('index.html')



@app.route('/checkout/<int:student_id>/<string:current_page>', methods=['POST']')
@login_required
def checkout(student_id):

    #Define the change we'll be making to the checkedOut column
    checked_out = {
        'checkedOut': True
    }
    #Additionally, find that student_id in our released_students array and remove it since they've been checked out)
    if student_id in released_students:
        released_students.remove(student_id)
    
    #Filter our student database by the given id, update all rows with that id to be checked out, and commit the changes
    student = db.session.query(student_tbl).filter_by(id=student_id).update(checked_out)
    db.session.commit()


    #Get the student's classroom and redirect back to that page once we're done updating the database
    temp = student_tbl.query.filter_by(id=student_id).first()

    classroom = temp.classNumber
    return redirect(url_for('table_view', room_number=classroom))

@app.route('/get_released_students', methods=["GET"])
def get_released_students():
    return jsonify(released_students)

@app.route('/update-released-students', methods=['POST'])
def update_released_students():
    released_students = request.get_json()
    # Update the released students in your database
    # The implementation will depend on your database
    return '', 200

@app.route('/add_to_released_students', methods=["POST"])
def add_to_released_students():
    student_id = request.json.get('studentId')
    if student_id not in released_students:
        released_students.append(student_id)
    return jsonify(success=True)

@app.route('/admin_view/database', methods=["GET", "POST"])
def table_view():
    #Grab all elements from our student_tbl & car_tbl and save them as arrays, where each cell is an element
    allStudents = student_tbl.query.all()
    allCars = car_tbl.query.all()
    studentList = []
    carList = []

    inFile = open("schedule.txt", "r")
    hour = inFile.readline()
    minute = inFile.readline()
    inFile.close()

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

    return render_template('table_view.html',
                           students=studentList,
                           cars=carList,
                           hour=hour.rstrip(),
                           minute=minute.rstrip())

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

@app.route('/admin_view/update_reset', methods=["GET", "POST"])
def change_db_reset():
    #Grab our new reset hour, minute, and ampm flag from our form
    newHour = request.form.get("resetHour")
    newMinute = request.form.get("resetMinute")
    ampm = request.form.get("ampmSelect")

    #If our ampm flag was 0, it means the time is in the AM
    if ampm == "0":
        #Double check if we're trying to set 12 AM, so we can set it to 0
        if int(newHour) == 12:
            newHour = 0
        #So we open schedule.txt and overwrite it wth our new hour and minute
        inFile = open("schedule.txt", "w")
        inFile.writelines([str(newHour), "\n", newMinute])
        inFile.close()
    #Otherwise we're looking at a PM time
    else:
        #In this case, we set newHour to an int instead of a string so we can add 12 to it, thus making it
        #a correct 24h time. However, we first check if we're trying to set 12 PM. If so, we skip.
        if int(newHour) != 12:
            newHour = int(newHour)
            newHour += 12
        #Then open schedule.txt and overwrite it wth our new hour and minute
        inFile = open("schedule.txt", "w")
        inFile.writelines([str(newHour), "\n", newMinute])
        inFile.close()

    #Reschedule our database reset job with our new time, so it takes effect immediately.
    scheduler.reschedule_job(job_id="resetScheduler", trigger='cron', hour=newHour, minute=newMinute)

    #Then return back to the database view
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
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        teacher_name = data.get('teacher_name')
        class_number = data.get('class_number')

        query = []
        if first_name:
            query.append(student_tbl.firstName == first_name)
        if last_name:
            query.append(student_tbl.lastName == last_name)
        if class_number:
            query.append(student_tbl.classNumber == class_number)

        students = student_tbl.query.filter(or_(*query)).all()

        students = student_tbl.query.filter(or_(*query)).all()
    
        serialized_students = [{
            'id': student.id,
            'firstName': student.firstName,
            'lastName': student.lastName,
            'classNumber': student.classNumber,
            'checkedOut': student.checkedOut
        } for student in students]

        return jsonify(serialized_students)


class StudentCheckoutAPI(Resource):
    def post(self, student_id):
        print(f"Student ID: {student_id}")  # Print the student ID

        student = student_tbl.query.filter_by(id=student_id).first()
        print(f"Student: {student}")  # Print the student object

        if student is None:
            return jsonify({'error': 'Not found'}), 404

        student.checkedOut = True
        db.session.commit()

        return jsonify({'message': 'Successfully checked out the student.'})


api.add_resource(StudentSearchAPI, '/api/search')
api.add_resource(StudentCheckoutAPI, '/api/checkout/<int:student_id>')


if __name__ == '__main__':
    app.run(debug=True)