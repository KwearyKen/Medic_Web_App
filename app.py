from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from io import BytesIO
import os

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'e5d3c8b16f7d8a5f96f2b79fa392b540'  # Replace with a secure key

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize Firebase
cred = credentials.Certificate('firebase_credentials.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'gs://medic-web-app-58ff7.firebasestorage.app'  # Replace with your actual bucket
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
            # Note: Firebase Admin SDK does not support password verification.
            # Normally, password verification should be handled on the client side using Firebase Client SDK.
            # For demonstration, we'll assume any existing user can log in.
            # Implement proper authentication in a production environment.
            
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
        pdfs = db.collection('pdfs').where('patient_id', '==', current_user.id).stream()
        pdf_list = [{'id': doc.id, 'pdf_url': doc.to_dict()['pdf_url'], 'upload_date': doc.to_dict()['upload_date']} for doc in pdfs]
        return render_template('patient_dashboard.html', pdfs=pdf_list)
        # Debugging PDFs for patients
        print("Fetching PDFs for patient ID:", patient_id)
        pdfs = db.collection('pdfs').where('patient_id', '==', patient_id).stream()
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
        # Assuming there's a field 'assigned_patients' as a list of patient IDs
        doctor_doc = db.collection('users').document(current_user.id).get()
        if not doctor_doc.exists:
            flash('Doctor not found.', 'danger')
            return redirect(url_for('login'))
        
        assigned_patients = doctor_doc.to_dict().get('assigned_patients', [])
         # Debugging: Print the assigned patients to check the data
        print("Assigned patients:", assigned_patients)
        records = []
        for patient_id in assigned_patients:
            patient_pdfs = db.collection('pdfs').where('patient_id', '==', patient_id).stream()
            for pdf in patient_pdfs:
                records.append({
                    'patient_id': patient_id,
                    'pdf_url': pdf.to_dict()['pdf_url'],
                    'upload_date': pdf.to_dict()['upload_date']
                })
        
        return render_template('doctor_dashboard.html', records=records)
    except Exception as e:
        print(f"Error fetching doctor PDFs: {e}")
        flash('Failed to retrieve patient PDFs.', 'danger')
        return redirect(url_for('login'))

# Route: Admin Dashboard
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    
    try:
        users = db.collection('users').stream()
        user_list = [{'id': doc.id, 'email': doc.to_dict()['email'], 'role': doc.to_dict()['role']} for doc in users]
        return render_template('admin_dashboard.html', users=user_list)
    except Exception as e:
        print(f"Error fetching users: {e}")
        flash('Failed to retrieve users.', 'danger')
        return redirect(url_for('login'))

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
        blob = bucket.blob(pdf_data['pdf_file'])
        pdf_content = blob.download_as_bytes()
        
        return send_file(
            BytesIO(pdf_content),
            attachment_filename=pdf_data['pdf_file'],
            as_attachment=True,
            mimetype='application/pdf'
        )
    
    except Exception as e:
        print(f"Error downloading PDF: {e}")
        flash('Failed to download PDF.', 'danger')
        return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
