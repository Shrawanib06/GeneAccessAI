import os
import re
import pandas as pd
from datetime import datetime
from flask import session

from user_auth.models import db, Report
from reports.generator import generate_custom_pdf_report, predict_disorder

# =========================
# Helpers: extractors
# =========================
def extract_name(text):
    text = re.sub(r'[*_`]', '', str(text))
    match = re.search(r"(my name is|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text, re.IGNORECASE)
    if match:
        return match.group(2).strip()
    words = [w for w in str(text).split() if w.istitle()]
    return ' '.join(words) if words else str(text).strip()

def extract_age(text):
    match = re.search(r'\b(\d{1,3})\b', str(text))
    return int(match.group(1)) if match else 0

def extract_numeric(text):
    m = re.search(r"[-+]?\d*\.?\d+", str(text))
    return float(m.group()) if m else 0.0

def norm_yes_no(text):
    t = str(text).strip().lower()
    if t in ["y", "yes", "yeah", "yep", "true"]: return "yes"
    if t in ["n", "no", "nope", "false"]: return "no"
    return "not sure"

def map_gender(text):
    t = str(text).strip().lower()
    if t in ["male", "m"]: return "Male"
    if t in ["female", "f"]: return "Female"
    return "Ambiguous"

def map_binary_yes_no(text):
    t = norm_yes_no(text)
    return "Yes" if t == "yes" else "No"

def map_birth_asphyxia(text):
    t = norm_yes_no(text)
    if t == "yes": return "Yes"
    if t == "no": return "No record"
    return "Not available"

def map_autopsy_birth_defect(text):
    t = str(text).strip().lower()
    if t in ["none", "no", "nil", "-", "not applicable", "na", "n/a", "unknown"]:
        return "None"
    return "Yes"

def map_maternal_paternal_gene(text):
    t = str(text).strip().lower()
    if t in ["no", "none", "nil", "-", "not detected", "n/a", "na", "null", "", "not sure", "unknown"]:
        return "No"
    return "Yes"

def map_blood_test_result(text):
    t = str(text).strip().lower()
    if t in ["normal", "n", "ok", "within range"]: return "normal"
    if any(k in t for k in ["high", "low", "abnormal", "slightly abnormal"]): return "slightly abnormal"
    return "inconclusive"

def map_respiratory_rate(value_text):
    t = str(value_text).strip().lower()
    if "tachyp" in t: return "Tachypnea"
    if "normal" in t: return "Normal (30-60)"
    m = re.search(r"[-+]?\d*\.?\d+", t)
    if m:
        val = float(m.group())
        return "Normal (30-60)" if 30 <= val <= 60 else "Tachypnea"
    return "Normal (30-60)"

def map_heart_rate(value_text):
    t = str(value_text).strip().lower()
    if "tachy" in t: return "Tachycardia"
    if "normal" in t: return "Normal"
    m = re.search(r"[-+]?\d*\.?\d+", t)
    if m:
        return "Tachycardia" if float(m.group()) > 100 else "Normal"
    return "Normal"

# =========================
# Chatbot
# =========================
class ChatbotFlow:
    def __init__(self):
        self.reset_session()

    def reset_session(self):
        self.chat_state = {
            'step': 0,
            'answers': {},
            'final_prediction': None,
            'report_pdf_path': None,
            'symptom_selection_pending': False
        }
        return "Welcome to GeneAccessAI. I'm Dr. GeneAccess. Let's begin. What's your full name?"

    def handle_input(self, message):
        step = self.chat_state['step']

        # --- Symptom selection handling ---
        if self.chat_state.get('symptom_selection_pending', False):
            try:
                selected_indices = [int(i.strip())-1 for i in str(message).split(",") if i.strip().isdigit()]
                selected_indices = [i for i in selected_indices if 0 <= i < len(self.chat_state['symptom_list'])]
                selected_symptoms = [self.chat_state['symptom_list'][i] for i in selected_indices]
                self.chat_state['answers']['Symptoms'] = selected_symptoms
                self.chat_state['symptom_selection_pending'] = False
                self.chat_state['step'] = 6
                return "Thank you. Did you experience trouble breathing at birth? (Birth asphyxia) (Yes / No / Not sure)"
            except Exception:
                return "Invalid input. Please enter numbers separated by commas."

        # --- Step-wise prompts ---
        steps_map = {
            0: ("name", extract_name, "How old are you?"),
            1: ("Patient Age", extract_age, "What is your gender? (Male / Female / Ambiguous)"),
            2: ("Gender", map_gender, "Does anyone in your family have genetic health problems? (Yes / No / Not sure)"),
            3: ("Family History", map_binary_yes_no, "Have there been any birth defects in your family? (If none, type 'None')"),
            4: ("Autopsy shows birth defect (if applicable)", map_autopsy_birth_defect, "symptom_selection"),
            5: ("History of anomalies in previous pregnancies", map_binary_yes_no, "Did you have trouble breathing when you were born? (Birth asphyxia)"),
            6: ("Birth asphyxia", map_birth_asphyxia, "Did your mother have any serious illness during pregnancy?"),
            7: ("H/O serious maternal illness", map_binary_yes_no, "Was your mother exposed to X-rays during pregnancy?"),
            8: ("H/O radiation exposure (x-ray)", map_binary_yes_no, "Was assisted conception (IVF/ART) used?"),
            9: ("Assisted conception IVF/ART", map_binary_yes_no, "How old was your mother when you were born?"),
            10: ("Mother's age", extract_numeric, "How old was your father when you were born?"),
            11: ("Father's age", extract_numeric, "How many previous abortions in the family?"),
            12: ("No. of previous abortion", lambda x: max(0,int(round(extract_numeric(x)))), "Did your mother take folic acid or vitamins during pregnancy?"),
            13: ("Folic acid details (peri-conceptional)", map_binary_yes_no, "Do you know if you inherited any genes from your mother's side?"),
            14: ("Genes in mother's side", map_binary_yes_no, "Do you know if you inherited any genes from your father's side?"),
            15: ("Inherited from father", map_binary_yes_no, "Any specific maternal gene detected?"),
            16: ("Maternal gene", map_maternal_paternal_gene, "Any specific paternal gene detected?"),
            17: ("Paternal gene", map_maternal_paternal_gene, "Do you know your blood cell count?"),
            18: ("Blood cell count (mcL)", lambda x: 4.8 if extract_numeric(x)==0 else float(extract_numeric(x)), "Do you know your white blood cell count?"),
            19: ("White Blood cell count (thousand per microliter)", lambda x: 7.0 if extract_numeric(x)==0 else float(extract_numeric(x)), "What was your recent blood test result?"),
            20: ("Blood test result", map_blood_test_result, "Do you know your breathing rate?"),
            21: ("Respiratory Rate (breaths/min)", map_respiratory_rate, "Do you know your heart rate?"),
            22: ("Heart Rate (rates/min", map_heart_rate, "Final step")
        }

        if step in steps_map:
            key, mapper, next_prompt = steps_map[step]
            val = mapper(message)
            self.chat_state['answers'][key] = val

            # Keep friendly duplicates
            if key == "name": self.chat_state['answers']['name'] = val
            if key == "Patient Age": self.chat_state['answers']['age'] = val
            if key == "Gender": self.chat_state['answers']['sex'] = val
            if key == "Family History": self.chat_state['answers']['family_history'] = val

            # Handle symptom selection
            if next_prompt == "symptom_selection":
                self.chat_state['symptom_list'] = [
                    "Cough","Wheezing","Frequent lung infections","Poor growth","Salty skin",
                    "Shortness of breath","Fatigue","Digestive problems","Clubbing of fingers",
                    "Nasal polyps","High blood sugar","Excessive thirst","Frequent urination",
                    "Blurred vision","Slow healing","Tingling/numbness","Weight loss",
                    "Increased hunger","Recurrent infections","Joint pain","Abdominal pain",
                    "Liver enlargement","Skin bronzing","Heart problems","Loss of libido",
                    "Memory problems","Vision loss","Central vision defect","Eye pain",
                    "Color vision problems","Visual hallucinations","Difficulty reading",
                    "Loss of depth perception","Optic disc swelling","Headaches",
                    "Developmental delay","Muscle weakness","Vomiting","Seizures",
                    "Breathing problems","Poor feeding","Hypotonia","Movement disorders",
                    "Lactic acidosis","Eye movement abnormalities","Exercise intolerance",
                    "Gastrointestinal problems","Tremors","Neuropathy","Loss of motor skills",
                    "Cherry-red spot","Muscle stiffness","Startle response",
                    "Difficulty swallowing","Poor coordination"
                ]
                self.chat_state['symptom_selection_pending'] = True
                return {
                    "type": "symptom_selection",
                    "message": "Please select the symptoms you have:",
                    "options": self.chat_state['symptom_list']
                }

            # --- Handle Final Step ---
            if next_prompt == "Final step":
                self.chat_state['step'] = "final_waiting"
                return {
                    "type": "wait_and_predict",
                    "message": "Please wait... Your genetic risk assessment report is being generated."
                }

            self.chat_state['step'] += 1
            return next_prompt

        # --- Handle waiting step (auto trigger final prediction) ---
        if step == "final_waiting":
            final_result = self._final_prediction()
            self.chat_state['step'] = "completed"
            return {
                "type": "final_result",
                "message": "Your comprehensive genetic risk assessment report has been generated.<br>" + final_result
            }

        return "Step not found."

    def _final_prediction(self):
        self.chat_state['final_prediction'] = None
        self.chat_state['report_pdf_path'] = None

        mapped_data = self._map_answers_to_model_features()
        pred, conf, _ = predict_disorder(mapped_data)
        self.chat_state['final_prediction'] = (
            f"Predicted Genetic Disorder Category: {pred} (Confidence: {conf*100:.2f}%)<br>"
        )

        self._generate_and_store_report(mapped_data)

        return self.chat_state['final_prediction'] + self._report_download_message()

    def _generate_and_store_report(self, mapped_data):
        try:
            path = generate_custom_pdf_report(mapped_data)
            self.chat_state['report_pdf_path'] = path
            user_id = session.get("user_id")
            if user_id:
                new_report = Report(
                    user_id=str(user_id),
                    filename=os.path.basename(path),
                    patient_name=mapped_data.get("name", "Unknown"),
                    date_of_birth=mapped_data.get("dob", datetime.now().strftime("%Y-%m-%d")),
                    sex=mapped_data.get("sex", "Unknown"),
                    sample_type="Genetic Sample",
                    ordering_doctor="AI Doctor",
                    lab_analyst="GeneAccessAI",
                )
                db.session.add(new_report)
                db.session.commit()
                print(f"✅ Report saved to DB: {new_report.filename}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Report generation failed: {e}")
            self.chat_state['report_pdf_path'] = None

    def _report_download_message(self):
        path = self.chat_state.get('report_pdf_path')
        if path and os.path.exists(path):
            return f"""
            <span>
            <a href='/api/chat/report/{os.path.basename(path)}' target='_blank' 
               style='display:inline-block;padding:10px 20px;
                      background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                      color:#fff;
                      border-radius:29px;
                      text-decoration:none;
                      margin-top:10px;
                      font-weight:600;
                      transition: 0.3s ease;
                      '
               onmouseover="this.style.background='linear-gradient(90deg, #764ba2 0%, #667eea 100%)'; this.style.transform='translateY(-2px) scale(1.04)';"
               onmouseout="this.style.background='linear-gradient(90deg, #667eea 0%, #764ba2 100%)'; this.style.transform='translateY(0) scale(1)';"
            >Download PDF Report</a>
        </span>
        <p style='margin-top:8px;'>This report is for educational purposes only and should be reviewed with healthcare professionals.</p>
        """
        return "<p>Report not available.</p>"

    def is_analysis_complete(self):
        return self.chat_state.get('final_prediction') is not None

    def get_report_path(self):
        return self.chat_state.get('report_pdf_path', None)

    def _map_answers_to_model_features(self):
        answers = dict(self.chat_state.get('answers', {}))
        if 'name' not in answers and 'name' in answers:
            answers['name'] = answers.get('name', '')
        answers['age'] = answers.get('age', answers.get('Patient Age', ''))
        answers['sex'] = answers.get('sex', answers.get('Gender', ''))
        answers['family_history'] = answers.get('family_history', answers.get('Family History', ''))

        selected = set(answers.get('Symptoms', []))
        symptom_columns = [
            "Cough","Wheezing","Frequent lung infections","Poor growth","Salty skin",
            "Shortness of breath","Fatigue","Digestive problems","Clubbing of fingers",
            "Nasal polyps","High blood sugar","Excessive thirst","Frequent urination",
            "Blurred vision","Slow healing","Tingling/numbness","Weight loss",
            "Increased hunger","Recurrent infections","Joint pain","Abdominal pain",
            "Liver enlargement","Skin bronzing","Heart problems","Loss of libido",
            "Memory problems","Vision loss","Central vision defect","Eye pain",
            "Color vision problems","Visual hallucinations","Difficulty reading",
            "Loss of depth perception","Optic disc swelling","Headaches",
            "Developmental delay","Muscle weakness","Vomiting","Seizures",
            "Breathing problems","Poor feeding","Hypotonia","Movement disorders",
            "Lactic acidosis","Eye movement abnormalities","Exercise intolerance",
            "Gastrointestinal problems","Tremors","Neuropathy","Loss of motor skills",
            "Cherry-red spot","Muscle stiffness","Startle response",
            "Difficulty swallowing","Poor coordination"
        ]
        for s in symptom_columns:
            if s not in answers:
                answers[s] = 1 if s in selected else 0
        return answers
