from app import db  # Import the db from Flask

class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    # Define other fields as needed

    def __init__(self, name):
        self.name = name

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    # Define other fields as needed

    def __init__(self, name, school_id):
        self.name = name
        self.school_id = school_id

class LicensePlate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    # Define other fields as needed

    def __init__(self, plate_number, student_id):
        self.plate_number = plate_number
        self.student_id = student_id
