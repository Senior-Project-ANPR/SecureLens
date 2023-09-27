from flask import Blueprint, render_template, redirect, url_for, flash, request
from app import db  # Import the db from Flask app
from models import Student
from forms import StudentForm  

students_bp = Blueprint('students', __name__, url_prefix='/students')

# Route to list all students
@students_bp.route('/')
def list_students():
    students = Student.query.all()
    return render_template('students/list.html', students=students)

# Route to display an individual student
@students_bp.route('/<int:student_id>')
def view_student(student_id):
    student = Student.query.get(student_id)
    if student:
        return render_template('students/view.html', student=student)
    else:
        flash('Student not found', 'error')
        return redirect(url_for('students.list_students'))

students_bp = Blueprint('students', __name__, url_prefix='/students')

# Create Student (GET and POST)
@students_bp.route('/create', methods=['GET', 'POST'])
def create_student():
    form = StudentForm()
    if form.validate_on_submit():
        student = Student(name=form.name.data)
        db.session.add(student)
        db.session.commit()
        flash('Student created successfully', 'success')
        return redirect(url_for('students.list_students'))
    return render_template('students/create.html', form=form)

# Read Students
@students_bp.route('/')
def list_students():
    students = Student.query.all()
    return render_template('students/list.html', students=students)

@students_bp.route('/<int:student_id>')
def view_student(student_id):
    student = Student.query.get(student_id)
    if student:
        return render_template('students/view.html', student=student)
    else:
        flash('Student not found', 'error')
        return redirect(url_for('students.list_students'))

# Update Student (GET and POST)
@students_bp.route('/<int:student_id>/update', methods=['GET', 'POST'])
def update_student(student_id):
    student = Student.query.get(student_id)
    if not student:
        flash('Student not found', 'error')
        return redirect(url_for('students.list_students'))

    form = StudentForm(obj=student)
    if form.validate_on_submit():
        student.name = form.name.data
        db.session.commit()
        flash('Student updated successfully', 'success')
        return redirect(url_for('students.view_student', student_id=student.id))
    return render_template('students/update.html', form=form, student=student)

# Delete Student (POST)
@students_bp.route('/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get(student_id)
    if student:
        db.session.delete(student)
        db.session.commit()
        flash('Student deleted successfully', 'success')
    else:
        flash('Student not found', 'error')
    return redirect(url_for('students.list_students'))
