from flask import Blueprint, request, redirect, url_for, flash, session, render_template
from .models import db, User
from .utils import hash_password, check_password

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    
    # POST request handling
    email = request.form['signup_email']
    password = request.form['signup_password']
    username = request.form.get('signup_username', '')

    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'error')
        return redirect(url_for('auth.signup'))

    # Create user with name field
    new_user = User(email=email, password=hash_password(password), status='Active', name=username)
    db.session.add(new_user)
    db.session.commit()
    flash('Signup successful. Please log in.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    # POST request handling
    email = request.form['login_email']
    password = request.form['login_password']

    user = User.query.filter_by(email=email).first()
    if user and check_password(user.password, password):
        session['user_id'] = user.id
        flash('Login successful!', 'success')
        return redirect(url_for('home'))
    else:
        flash('Invalid credentials.', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('home'))
