import firebase_admin
from firebase_admin import credentials, auth, storage, firestore
import datetime

def initialize_firebase():
    """Initialize Firebase Admin SDK for both Authentication and Storage."""
    try:
        # Path to your service account key file
        cred_path = r"D:\Python project\Medic_Web_App\Medic_Web_App\firebase_credentials.json"

        # Initialize Firebase Admin SDK
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'projectId': 'medic-web-app-58ff7',  # Authentication project
            'storageBucket': 'medic-web-app-58ff7.firebasestorage.app'  # Correct bucket for storage
        })
        print("Firebase initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize Firebase: {e}")

def authenticate_user(email, password):
    """Authenticate a user and retrieve their UID."""
    try:
        # Emulating login functionality (Admin SDK doesn't support password-based sign-in)
        # Get the user by email
        user = auth.get_user_by_email(email)
        uid = user.uid
        print(f"Authenticated user: {email}, UID: {uid}")
        return uid
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None

def upload_file_to_storage(uid, file_path):
    """Upload a file to Firebase Storage in the user's directory and update Firestore."""
    try:
        bucket = storage.bucket()
        db = firestore.client()

        # Extract the filename from the provided file path
        file_name = file_path.split("\\")[-1]

        # Set the destination path: /pdfs/<UID>/<file_name>
        destination_path = f"pdfs/{uid}/{file_name}"
        blob = bucket.blob(destination_path)

        # Upload the file
        blob.upload_from_filename(file_path)
        print(f"File uploaded successfully to: {destination_path}")

        # Make the file publicly accessible
        blob.make_public()

        # Generate a public URL for the file
        pdf_url = blob.public_url

        # Update Firestore collection
        pdf_data = {
            'patient_id': uid,
            'pdf_file': destination_path,
            'pdf_url': pdf_url,
            'upload_date': datetime.datetime.now()
        }
        db.collection('pdfs').add(pdf_data)
        print(f"Firestore updated with PDF metadata: {pdf_data}")

    except Exception as e:
        print(f"Failed to upload file: {e}")

if __name__ == "__main__":
    # Initialize Firebase
    initialize_firebase()

    # Use specified email, password, and file path
    user_email = "patient1@email.com"
    user_password = "123456"
    file_to_upload = r"D:\Python project\Kenneth_2024-11-21_03-26-38_health_report.pdf"

    # Authenticate user and get UID
    user_uid = authenticate_user(user_email, user_password)
    if user_uid:
        # Upload a file to the user's directory
        upload_file_to_storage(user_uid, file_to_upload)
