from flask import Flask, render_template, request, redirect, url_for, session, flash
import requests
import boto3
from botocore.exceptions import NoCredentialsError
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# AWS Config
S3_BUCKET = 'ccit-project5'
S3_REGION = 'ap-south-2'
CLOUDFRONT_DOMAIN = 'd2svc8nm4d0v3c.cloudfront.net'
AWS_ACCESS_KEY = 'AK'
AWS_SECRET_KEY = 'SAK'

# Lambda API URLs
SIGNUP_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/SignUp"
SIGNIN_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/Signin"
WELCOME_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/welcome"
LIST_BOOKS_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/ListBooks"
BARROW_BOOKS_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/barrowbooks"
RETURN_BOOKS_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/ReturnBooks"
GET_BARROWED_BOOKS_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/Getbarrowedbooks"
GET_BARROWED_BOOKS_HISTORY_API_URL = "https://tx1oq6tbb7.execute-api.ap-south-2.amazonaws.com/prod/GetBorrowHistory"

# AWS S3 Client
s3_client = boto3.client(
    's3',
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name         = request.form['name']
        mobile       = request.form['mobile']
        email        = request.form['email']
        raw_password = request.form['password']
        re_password  = request.form['re_password']
        gender       = request.form['gender']
        location     = request.form['location']
        user_image   = request.files.get('image')

        if raw_password != re_password:
            flash('Passwords do not match')
            return redirect(url_for('signup'))

        filename = ''
        if user_image and user_image.filename:
            filename = user_image.filename
            try:
                s3_client.upload_fileobj(
                    user_image,
                    S3_BUCKET,
                    filename,
                    ExtraArgs={'ContentType': user_image.content_type}
                )
            except Exception as e:
                flash('S3 upload failed: ' + str(e))
                return redirect(url_for('signup'))

        params = {
            'name':     name,
            'mobile':   mobile,
            'email':    email,
            'password': raw_password,
            'gender':   gender,
            'location': location,
            'image':    filename
        }

        try:
            response = requests.get(SIGNUP_API_URL, params=params)
            if response.status_code == 200:
                flash('Signup successful! Please login.')
                return redirect(url_for('login'))
            else:
                body = response.json()
                error = body.get('message') or body.get('body') or 'Unknown error'
                flash(f'Signup failed: {error}')
        except Exception as e:
            flash('Signup API call failed: ' + str(e))

    return render_template('signup.html')

@app.route('/signin', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        payload = {"email": email, "password": password}
        response = requests.get(SIGNIN_API_URL, params=payload)

        if response.status_code == 200:
            try:
                user_data = response.json()
                body_data = user_data.get("body")
                body_json = json.loads(body_data) if isinstance(body_data, str) else body_data
                user = body_json.get("user")

                if user:
                    session['user_id'] = user.get("id")
                    session['username'] = user.get("name")
                    session['email'] = user.get("email")
                    session['image_url'] = f"https://{CLOUDFRONT_DOMAIN}/{user.get('image')}" if user.get("image") else None
                    return redirect(url_for('welcome'))
                else:
                    flash("Invalid Credentials")
            except Exception as e:
                flash(f"Login parsing error: {e}")
        else:
            flash("Invalid Credentials")

    return render_template('login.html')

@app.route('/welcome')
def welcome():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    try:
        response = requests.get(WELCOME_API_URL, params={'user_id': user_id})
        if response.status_code == 200:
            outer_data = response.json()
            body_data = outer_data.get("body")
            body_json = json.loads(body_data) if isinstance(body_data, str) else body_data
            user = body_json.get("user")
            image_url = f"https://{CLOUDFRONT_DOMAIN}/{user['image']}" if user.get("image") else None
            return render_template('welcome.html', user=user, image_url=image_url)
        else:
            flash('Failed to fetch user data.')
    except Exception as e:
        flash(f'Lambda call error: {str(e)}')

    return redirect(url_for('login'))

@app.route('/user', methods=['GET', 'POST'])
def user_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Borrow / Return handling
    if request.method == 'POST':
        action = request.form.get('action')
        book_id = request.form.get('book_id')

        if not action or not book_id:
            flash('Invalid action or book ID')
            return redirect(url_for('user_page'))

        api_url = BARROW_BOOKS_API_URL if action == 'borrow' else RETURN_BOOKS_API_URL
        try:
            payload = {'user_id': user_id, 'book_id': book_id}
            r = requests.get(api_url, params=payload)

            if r.status_code == 200:
                body = r.json().get("body")
                msg = json.loads(body) if isinstance(body, str) else body
                flash(msg)
            else:
                flash(f"❌ {action.title()} API failed.")
        except Exception as e:
            flash(f"{action.title()} Lambda error: {e}")

        return redirect(url_for('user_page'))

    # Get list of books
    try:
        r = requests.get(LIST_BOOKS_API_URL)
        books = [(b["id"], b["title"], b["author"]) for b in json.loads(r.json()["body"]).get("books", [])]
    except Exception as e:
        flash(f"Books Lambda error: {e}")
        books = []

    # Get currently borrowed books
    try:
        r = requests.get(GET_BARROWED_BOOKS_API_URL, params={"user_id": user_id})
        borrowed_books = [(b["id"], b["title"], b["author"]) for b in json.loads(r.json()["body"]).get("borrowed_books", [])]
    except Exception as e:
        flash(f"BorrowedBooks Lambda error: {e}")
        borrowed_books = []

    # Get borrow history
    def safe_parse(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except:
            return None

    try:
        r = requests.get(GET_BARROWED_BOOKS_HISTORY_API_URL, params={"user_id": user_id})
        hist_raw = json.loads(r.json()["body"]).get("history", [])
        history = [
            (
                h["title"],
                h["author"],
                safe_parse(h["borrow_date"]),
                safe_parse(h["return_date"]),
                h["id"]
            ) for h in hist_raw
        ]
    except Exception as e:
        flash(f"History Lambda error: {e}")
        history = []

    return render_template('user.html', books=books, borrowed_books=borrowed_books, history=history)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)