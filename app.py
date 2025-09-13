from flask import Flask, render_template, session, redirect, url_for, request, jsonify, send_from_directory, flash
from user_auth.models import db, Report, User, ChatSession, Query
from user_auth.auth_routes import auth_bp
import os
from reports.generator import generate_custom_pdf_report
import pandas as pd
from ai_engine.chatbot.intent_handler import IntentHandler
from ai_engine.chatbot.chatbot_flow import ChatbotFlow

app = Flask(__name__)
app.config['SECRET_KEY'] = '86d36c4a2452f1f4c426f0c25423d686868d81068d10be5d7182fca2d995000e'
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'database', 'geneaccess.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
app.register_blueprint(auth_bp)

# Initialize chatbot handler
# chatbot_handler = IntentHandler()

# ... (keep your existing app.py code, just ensure the chatbot reset works properly)

@app.route('/')
@app.route('/')
def home():
    user = None
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        
        # ✅ Always reset chatbot state on page reload
        chatbot_flow = ChatbotFlow()
        initial_response = chatbot_flow.reset_session()
        # Clear any existing chat state completely
        if 'chat_state' in session:
            session.pop('chat_state', None)
        # Start fresh
        session['chat_state'] = chatbot_flow.chat_state.copy()

    return render_template('index.html', user=user)

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chatbot messages"""
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        message = data.get('message', '')
        # Record the query
        chat_session_id = session.get('chat_session_id')
        if chat_session_id:
            query = Query(user_id=int(session['user_id']), chat_session_id=chat_session_id, content=message)
            db.session.add(query)
            db.session.commit()
        # Per-user chatbot state
        chatbot_flow = ChatbotFlow()
        if 'chat_state' in session:
            # Restore state (convert set back from list if needed)
            chat_state = session['chat_state']
            if 'asked_questions' in chat_state and isinstance(chat_state['asked_questions'], list):
                chat_state['asked_questions'] = set(chat_state['asked_questions'])
            chatbot_flow.chat_state = chat_state
        response = chatbot_flow.handle_input(message)
        # Save updated state (convert set to list for session serialization)
        chat_state_to_save = chatbot_flow.chat_state.copy()
        if 'asked_questions' in chat_state_to_save and isinstance(chat_state_to_save['asked_questions'], set):
            chat_state_to_save['asked_questions'] = list(chat_state_to_save['asked_questions'])
        session['chat_state'] = chat_state_to_save
        report_info = None
        if chatbot_flow.is_analysis_complete():
            report_path = chatbot_flow.get_report_path()
            if report_path and os.path.exists(report_path):
                report_info = {
                    'filename': os.path.basename(report_path),
                    'download_url': url_for('download_chatbot_report', filename=os.path.basename(report_path))
                }
        return jsonify({
            'success': True,
            'response': response,
            'analysis_complete': chatbot_flow.is_analysis_complete(),
            'report_info': report_info
        })
    # except Exception as e:
    #     return jsonify({'error': f'Chat error: {str(e)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()  # ✅ Print full error in terminal
        return jsonify({'error': f'Chat error: {str(e)}'}), 500


@app.route('/api/chat/reset', methods=['POST'])
def reset_chat():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        # Start a new chat session for the user
        chat_session = ChatSession(user_id=int(session['user_id']))
        db.session.add(chat_session)
        db.session.commit()
        session['chat_session_id'] = chat_session.id
        chatbot_flow = ChatbotFlow()
        response = chatbot_flow.reset_session()
        # Save new state to session
        chat_state_to_save = chatbot_flow.chat_state.copy()
        if 'asked_questions' in chat_state_to_save and isinstance(chat_state_to_save['asked_questions'], set):
            chat_state_to_save['asked_questions'] = list(chat_state_to_save['asked_questions'])
        session['chat_state'] = chat_state_to_save
        return jsonify({
            'success': True,
            'response': response
        })
    except Exception as e:
        return jsonify({'error': f'Reset error: {str(e)}'}), 500

@app.route('/api/chat/report', methods=['GET'])
def get_chatbot_report():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        chatbot_flow = ChatbotFlow()
        if 'chat_state' in session:
            chat_state = session['chat_state']
            if 'asked_questions' in chat_state and isinstance(chat_state['asked_questions'], list):
                chat_state['asked_questions'] = set(chat_state['asked_questions'])
            chatbot_flow.chat_state = chat_state
        if not chatbot_flow.is_analysis_complete():
            return jsonify({'error': 'Analysis not complete'}), 400
        report_path = chatbot_flow.get_report_path()
        if not report_path or not os.path.exists(report_path):
            return jsonify({'error': 'Report not found'}), 404
        return jsonify({
            'success': True,
            'filename': os.path.basename(report_path),
            'download_url': url_for('download_chatbot_report', filename=os.path.basename(report_path))
        })
    except Exception as e:
        return jsonify({'error': f'Report error: {str(e)}'}), 500

@app.route('/api/chat/report/<filename>')
def download_chatbot_report(filename):
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        # ✅ Accept both chatbot_report_ and geneaccess_report_ filenames
        if not (filename.startswith('report_') or filename.startswith('chatbot_report_') or filename.startswith('geneaccess_report_')):
            return jsonify({'error': 'Invalid report file'}), 400

        reports_dir = os.path.join(os.path.dirname(__file__), "reports", "exports")
        return send_from_directory(reports_dir, filename, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

@app.route('/report')
def report():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    user = db.session.get(User, session['user_id'])
    reports = Report.query.filter_by(user_id=str(user.id)).order_by(Report.created_at.desc()).all()
    return render_template('report.html', user=user, reports=reports)

@app.route('/user')
def user_profile():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    user = db.session.get(User, session['user_id'])
    report_count = Report.query.filter_by(user_id=str(user.id)).count()
    chat_count = ChatSession.query.filter_by(user_id=user.id).count()
    query_count = Query.query.filter_by(user_id=user.id).count()
    recent_activity = [
        f"{q.timestamp.strftime('%Y-%m-%d %H:%M')}: {q.content}"
        for q in Query.query.filter_by(user_id=user.id).order_by(Query.timestamp.desc()).limit(5)
    ]
    return render_template('user.html', user=user, report_count=report_count, chat_count=chat_count, query_count=query_count, recent_activity=recent_activity)

@app.route('/reports/<filename>')
def download_report(filename):
    return send_from_directory('reports', filename, as_attachment=True)

@app.route('/api/chat/patient_info', methods=['POST'])
def set_patient_info():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.get_json()
    chatbot_flow = ChatbotFlow()
    if 'chat_state' in session:
        chat_state = session['chat_state']
        if 'answers' in chat_state:
            chat_state['answers']['patient_name'] = data.get('patient_name', '')
            chat_state['answers']['sex'] = data.get('sex', '')
            chat_state['answers']['age'] = data.get('age', '')
            chat_state['answers']['dob'] = data.get('dob', '')
            chat_state['step'] = 1 # Assuming step is 1 after patient info is set
            # Save updated state to session
            if 'asked_questions' in chat_state and isinstance(chat_state['asked_questions'], set):
                chat_state['asked_questions'] = list(chat_state['asked_questions'])
            session['chat_state'] = chat_state
    chatbot_flow.chat_state = chat_state # Ensure chat_state is updated in the flow
    return jsonify({'success': True})

@app.route('/update_profile', methods=['GET', 'POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    user = db.session.get(User, session['user_id'])
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        from user_auth.utils import hash_password, check_password
        if new_name and new_name != user.name:
            user.name = new_name
            db.session.commit()
            flash('Name updated successfully.', 'success')
        if new_email and new_email != user.email:
            if User.query.filter_by(email=new_email).first():
                flash('Email already in use.', 'error')
            else:
                user.email = new_email
                db.session.commit()
                flash('Email updated successfully.', 'success')
        if current_password and new_password and confirm_password:
            if not check_password(user.password, current_password):
                flash('Current password is incorrect.', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match.', 'error')
            else:
                user.password = hash_password(new_password)
                db.session.commit()
                flash('Password updated successfully.', 'success')
        return redirect(url_for('update_profile'))
    return render_template('update_profile.html', user=user)

@app.route('/api/report/delete/<filename>', methods=['DELETE'])
def delete_report(filename):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = str(session['user_id'])
    report = Report.query.filter_by(user_id=user_id, filename=filename).first()
    if not report:
        return jsonify({'success': False, 'error': 'Report not found'}), 404
    report_path = os.path.join('reports', filename)
    try:
        if os.path.exists(report_path):
            os.remove(report_path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'File delete error: {str(e)}'}), 500
    try:
        db.session.delete(report)
        db.session.commit()
    except Exception as e:
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    return jsonify({'success': True})

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    user = db.session.get(User, session['user_id'])
    if not user:
        flash("User not found.", "error")
        return redirect(url_for('user_profile'))

    try:
        # Delete user's reports
        Report.query.filter_by(user_id=str(user.id)).delete()
        # Delete user's chat sessions and queries
        ChatSession.query.filter_by(user_id=user.id).delete()
        Query.query.filter_by(user_id=user.id).delete()
        # Finally delete user
        db.session.delete(user)
        db.session.commit()
        
        session.clear()  # ✅ Log them out
        flash("Account deleted successfully.", "success")
        return redirect(url_for('home'))
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting account: {str(e)}", "error")
        return redirect(url_for('user_profile'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
