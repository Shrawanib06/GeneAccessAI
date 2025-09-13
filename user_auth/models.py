from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(32), default='Active')

    def __repr__(self):
        return f'<User {self.email}>'

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(128), nullable=False)
    filename = db.Column(db.String(256), nullable=False)
    patient_name = db.Column(db.String(128), nullable=False)
    date_of_birth = db.Column(db.String(32), nullable=False)
    sex = db.Column(db.String(32), nullable=False)
    sample_type = db.Column(db.String(64), nullable=False)
    ordering_doctor = db.Column(db.String(128), nullable=False)
    lab_analyst = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Report {self.filename} for user {self.user_id}>'

class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    queries = db.relationship('Query', backref='chat_session', lazy=True)

class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    chat_session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'))
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
