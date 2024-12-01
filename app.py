from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from io import BytesIO
import os
import ast
from datetime import datetime
from google.cloud.firestore_v1 import FieldFilter

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'firebase secret key'  # Replace with a secure key

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize Firebase
cred = credentials.Certificate('firebase credential file here')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'firebase bucket here'  # Ensure this matches your Firebase project
})
db = firestore.client()
bucket = storage.bucket()

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, uid, email, role):
        self.id = uid
        self.email = email
        self.role = role

# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    try:
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return User(uid=user_id, email=user_data['email'], role=user_data['role'])
    except Exception as e:
        print(f"Error loading user: {e}")
    return None

# Route: Home redirects to login
@app.route('/')
def index():
    return redirect(url_for('login'))

# Route: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            # Firebase Authentication: Sign in user
            user = auth.get_user_by_email(email)
            user_data = db.collection('users').document(user.uid).get().to_dict()
            login_user(User(uid=user.uid, email=email, role=user_data['role']))
            flash('Logged in successfully.', 'success')

            if user_data['role'] == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user_data['role'] == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            elif user_data['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid user role.', 'danger')
                return redirect(url_for('login'))

        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please check your credentials.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

# Route: Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Route: Patient Dashboard
@app.route('/patient_dashboard')
@login_required
def patient_dashboard():
    if current_user.role != 'patient':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    try:
        # Fetch PDFs for the logged-in patient, sorted by upload_date in descending order
        pdfs = db.collection('pdfs').where(filter=FieldFilter('patient_id', '==', current_user.id)).order_by('upload_date', direction=firestore.Query.DESCENDING).stream()

        # Generate list of PDFs for the patient
        pdf_list = []
        for pdf in pdfs:
            pdf_data = pdf.to_dict()
            pdf_list.append({
                'id': pdf.id,
                'pdf_url': pdf_data['pdf_url'],  # URL pointing to the PDF in Firebase Storage
                'upload_date': pdf_data['upload_date'],  # Use the string value directly
                'message': None
            })

        # Debugging: Print the fetched PDFs
        print("Fetched PDFs for patient:", pdf_list)

        # If no PDFs are found for the patient, provide a placeholder message
        if not pdf_list:
            flash('No PDF records found.', 'info')
            return render_template('patient_dashboard.html', pdfs=[])

        return render_template('patient_dashboard.html', pdfs=pdf_list)

    except Exception as e:
        print(f"Error fetching PDFs: {e}")
        flash('Failed to retrieve PDFs.', 'danger')
        return redirect(url_for('login'))

# Route: Doctor Dashboard
@app.route('/doctor_dashboard')
@login_required
def doctor_dashboard():
    if current_user.role != 'doctor':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    try:
        # Fetch the doctor's document
        doctor_doc = db.collection('users').document(current_user.id).get()
        if not doctor_doc.exists:
            flash('Doctor not found.', 'danger')
            return redirect(url_for('login'))

        # Retrieve assigned patients and safely convert the string to a list
        assigned_patients_str = doctor_doc.to_dict().get('assigned_patients', '[]')
        assigned_patients = ast.literal_eval(assigned_patients_str)

        # Fetch patient details
        patients = []
        for patient_id in assigned_patients:
            patient_doc = db.collection('users').document(patient_id).get()
            if patient_doc.exists:
                patient_data = patient_doc.to_dict()
                patients.append({
                    'id': patient_id,
                    'email': patient_data['email']
                })

        return render_template('doctor_dashboard.html', patients=patients)
    except Exception as e:
        print(f"Error fetching doctor dashboard: {e}")
        flash('Failed to retrieve patient information.', 'danger')
        return redirect(url_for('login'))

# Route: View Patient PDFs
@app.route('/view_patient_pdfs/<patient_id>')
@login_required
def view_patient_pdfs(patient_id):
    if current_user.role != 'doctor':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    try:
        # Fetch PDFs for the specified patient, sorted by upload_date in descending order
        pdfs = db.collection('pdfs').where(filter=FieldFilter('patient_id', '==', patient_id)).order_by('upload_date', direction=firestore.Query.DESCENDING).stream()

        # Generate list of PDFs for the patient
        pdf_list = []
        for pdf in pdfs:
            pdf_data = pdf.to_dict()
            pdf_list.append({
                'id': pdf.id,
                'pdf_url': pdf_data['pdf_url'],  # URL pointing to the PDF in Firebase Storage
                'upload_date': pdf_data['upload_date'],  # Use the string value directly
                'message': None
            })

        # Debugging: Print the fetched PDFs
        print("Fetched PDFs for patient:", pdf_list)

        # If no PDFs are found for the patient, provide a placeholder message
        if not pdf_list:
            flash('No PDF records found.', 'info')
            return render_template('view_patient_pdfs.html', pdfs=[])

        return render_template('view_patient_pdfs.html', pdfs=pdf_list, patient_id=patient_id)

    except Exception as e:
        print(f"Error fetching PDFs: {e}")
        flash('Failed to retrieve PDFs.', 'danger')
        return redirect(url_for('doctor_dashboard'))

# Route: Admin Dashboard
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    try:
        users = db.collection('users').where('role', '!=', 'admin').stream()
        user_list = [{'id': doc.id, 'email': doc.to_dict()['email'], 'role': doc.to_dict()['role']} for doc in users]
        return render_template('admin_dashboard.html', users=user_list)
    except Exception as e:
        print(f"Error fetching users: {e}")
        flash('Failed to retrieve users.', 'danger')
        return redirect(url_for('login'))


# Route: Sign Up Doctor
@app.route('/signup_doctor', methods=['GET', 'POST'])
@login_required
def signup_doctor():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            # Create user in Firebase Authentication
            user = auth.create_user(email=email, password=password)
            # Add user to Firestore
            db.collection('users').document(user.uid).set({
                'email': email,
                'role': 'doctor',
                'assigned_patients': '[]'
            })
            flash('Doctor signed up successfully.', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Error signing up doctor: {e}")
            flash('Failed to sign up doctor.', 'danger')
            return redirect(url_for('signup_doctor'))

    return render_template('signup_doctor.html')

# Route: Sign Up Patient
@app.route('/signup_patient', methods=['GET', 'POST'])
@login_required
def signup_patient():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            # Create user in Firebase Authentication
            user = auth.create_user(email=email, password=password)
            # Add user to Firestore
            db.collection('users').document(user.uid).set({
                'email': email,
                'role': 'patient'
            })
            flash('Patient signed up successfully.', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Error signing up patient: {e}")
            flash('Failed to sign up patient.', 'danger')
            return redirect(url_for('signup_patient'))

    return render_template('signup_patient.html')

# Route: Assign/Unassign Patient
@app.route('/assign_unassign_patient', methods=['GET', 'POST'])
@login_required
def assign_unassign_patient():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        doctor_id = request.form['doctor_id']
        patient_id = request.form['patient_id']
        action = request.form['action']

        try:
            # Fetch the doctor's document
            doctor_doc = db.collection('users').document(doctor_id).get()
            if not doctor_doc.exists:
                flash('Doctor not found.', 'danger')
                return redirect(url_for('assign_unassign_patient'))

            # Update the doctor's assigned patients
            assigned_patients_str = doctor_doc.to_dict().get('assigned_patients', '[]')
            assigned_patients = ast.literal_eval(assigned_patients_str)

            if action == 'assign':
                if patient_id not in assigned_patients:
                    assigned_patients.append(patient_id)
                    db.collection('users').document(doctor_id).update({
                        'assigned_patients': str(assigned_patients)
                    })
                    flash('Patient assigned to doctor successfully.', 'success')
                else:
                    flash('Patient already assigned to this doctor.', 'info')
            elif action == 'unassign':
                if patient_id in assigned_patients:
                    assigned_patients.remove(patient_id)
                    db.collection('users').document(doctor_id).update({
                        'assigned_patients': str(assigned_patients)
                    })
                    flash('Patient unassigned from doctor successfully.', 'success')
                else:
                    flash('Patient not assigned to this doctor.', 'info')

            return redirect(url_for('assign_unassign_patient'))
        except Exception as e:
            print(f"Error assigning/unassigning patient: {e}")
            flash('Failed to assign/unassign patient.', 'danger')
            return redirect(url_for('assign_unassign_patient'))

    try:
        doctors = db.collection('users').where('role', '==', 'doctor').stream()
        patients = db.collection('users').where('role', '==', 'patient').stream()
        doctors_list = [{'id': doc.id, 'email': doc.to_dict()['email']} for doc in doctors]
        patients_list = [{'id': doc.id, 'email': doc.to_dict()['email']} for doc in patients]
        return render_template('assign_unassign_patient.html', doctors=doctors_list, patients=patients_list)
    except Exception as e:
        print(f"Error fetching doctors and patients: {e}")
        flash('Failed to retrieve doctors and patients.', 'danger')
        return redirect(url_for('login'))


# Route: Edit User
@app.route('/edit_user/<user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            # Update user in Firebase Authentication
            auth.update_user(user_id, email=email)
            if password:
                auth.update_user(user_id, password=password)

            # Update user in Firestore
            db.collection('users').document(user_id).update({
                'email': email
            })
            flash('User updated successfully.', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Error updating user: {e}")
            flash('Failed to update user.', 'danger')
            return redirect(url_for('edit_user', user_id=user_id))

    try:
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return render_template('edit_user.html', user=user_data, user_id=user_id)
        else:
            flash('User not found.', 'danger')
            return redirect(url_for('admin_dashboard'))
    except Exception as e:
        print(f"Error fetching user: {e}")
        flash('Failed to retrieve user.', 'danger')
        return redirect(url_for('admin_dashboard'))



# Route: Delete User
@app.route('/delete_user/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    try:
        # Fetch the user document to check the role
        user_doc = db.collection('users').document(user_id).get()
        if not user_doc.exists:
            flash('User not found.', 'danger')
            return redirect(url_for('admin_dashboard'))

        user_data = user_doc.to_dict()

        # If the user is a patient, remove their ID from the assigned patients list of any doctor
        if user_data['role'] == 'patient':
            doctors = db.collection('users').where('role', '==', 'doctor').stream()
            for doctor_doc in doctors:
                doctor_data = doctor_doc.to_dict()
                assigned_patients_str = doctor_data.get('assigned_patients', '[]')
                assigned_patients = ast.literal_eval(assigned_patients_str)

                if user_id in assigned_patients:
                    assigned_patients.remove(user_id)
                    db.collection('users').document(doctor_doc.id).update({
                        'assigned_patients': str(assigned_patients)
                    })

        # Delete user from Firebase Authentication
        auth.delete_user(user_id)
        # Delete user from Firestore
        db.collection('users').document(user_id).delete()
        flash('User deleted successfully.', 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        print(f"Error deleting user: {e}")
        flash('Failed to delete user.', 'danger')
        return redirect(url_for('admin_dashboard'))

# Route: Download PDF
@app.route('/download_pdf/<pdf_id>')
@login_required
def download_pdf(pdf_id):
    try:
        pdf_record = db.collection('pdfs').document(pdf_id).get()
        if not pdf_record.exists:
            flash('PDF not found.', 'danger')
            return redirect(url_for('login'))

        pdf_data = pdf_record.to_dict()
        print(f"PDF Data: {pdf_data}")  # Debugging line

        # Access Control
        if current_user.role == 'patient' and pdf_data['patient_id'] != current_user.id:
            flash('Access denied.', 'danger')
            return redirect(url_for('login'))

        if current_user.role == 'doctor':
            doctor_doc = db.collection('users').document(current_user.id).get()
            if not doctor_doc.exists or pdf_data['patient_id'] not in doctor_doc.to_dict().get('assigned_patients', []):
                flash('Access denied.', 'danger')
                return redirect(url_for('login'))

        # Fetch PDF from Firebase Storage
        pdf_file_path = pdf_data['pdf_file']  # Path of the file stored in Firebase Storage
        print(f"Fetching PDF from path: {pdf_file_path}")  # Debugging line
        blob = bucket.blob(pdf_file_path)
        pdf_content = blob.download_as_bytes()

        return send_file(
            BytesIO(pdf_content),
            attachment_filename=pdf_data['pdf_file'].split('/')[-1],  # Only use the filename as the attachment
            as_attachment=True,
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error downloading PDF: {e}")
        flash('Failed to download PDF.', 'danger')
        return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
