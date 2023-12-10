from operator import or_
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
from flask_cors import CORS

app = Flask(__name__)
boostrap = Bootstrap(app)
CORS(app)

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
                cv2.putText(image, class_name.upper(), (int(x1), int(y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3, cv2.LINE_AA)

                if class_name == 'plate':
                    plate_image = image[int(y1):int(y2), int(x1):int(x2)]
                    gray_plate = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
                    ocr_results = reader.readtext(gray_plate)

                    detected_text = ' '.join([item[1] for item in ocr_results]).strip()

                    if detected_text:
                        cv2.putText(image, "License Plate: " + detected_text, (int(x1), int(y1 - 40)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    with app.app_context():
                        tempStudent = student_tbl.query.filter_by(carPlate=detected_text).all()
                        if tempStudent:
                            for record in tempStudent:
                                tempFirstName = record.firstName
                                tempLastName = record.lastName
                                tempClassroom = record.classroom
                                print(
                                    f"License Plate Recognized. Student: {tempFirstName} {tempLastName}, Classroom: {tempClassroom}")

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

@app.route('/release/<int:classroom>')
@login_required
def release_students(room_number):
    #Filter our student database down to only the students in the given classroom and pass that on to our
    #HTML template
    students = student_tbl.query.filter_by(classNumber=room_number).all()
    return render_template('release_students.html', students=students, classNumber=room_number)

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
                return redirect('admin_view')
            else:
                return jsonify(success=True, message="Login Successful")
            

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
    classroom = temp.classroom
    return redirect(url_for('release_students', classroom=classroom))

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
            return jsonify({'error' : 'Not found'}), 404

        student.checkedOut = True
        db.session.commit()

        return jsonify({'message' : 'Successfully checked out the student.'})

api.add_resource(StudentSearchAPI, '/api/search')
api.add_resource(StudentCheckoutAPI, '/api/checkout/<int:student_id>')


if __name__ == '__main__':
    app.run(debug=True)