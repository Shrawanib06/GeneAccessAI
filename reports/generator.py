import os
from datetime import datetime
import joblib
import pandas as pd
import numpy as np

# PDF generation
try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
except Exception:
    XHTML2PDF_AVAILABLE = False

# ----------------------------------------------------
# Model path + cache
# ----------------------------------------------------
# Default: <repo_root>/ai_engine/genetic_disorder_model.pkl
THIS_DIR = os.path.dirname(__file__)
DEFAULT_MODEL_PATH = os.path.abspath(os.path.join(THIS_DIR, "..", "ai_engine", "genetic_disorder_model.pkl"))
MODEL_PATH = os.environ.get("GENEACCESS_MODEL_PATH", DEFAULT_MODEL_PATH)

_CACHED_MODEL_PACKAGE = None  # {'model': pipeline, 'label_encoder': ..., 'feature_names': [...]}

# Symptoms used in training
SYMPTOM_COLUMNS = [
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

# Categorical clinical fields present in training
CATEGORICAL_FIELDS = [
    "Gender",
    "Birth asphyxia",
    "Autopsy shows birth defect (if applicable)",
    "Folic acid details (peri-conceptional)",
    "H/O serious maternal illness",
    "H/O radiation exposure (x-ray)",
    "H/O substance abuse",
    "Assisted conception IVF/ART",
    "History of anomalies in previous pregnancies",
    "Blood test result",
    "Respiratory Rate (breaths/min)",
    "Heart Rate (rates/min"
]

# Numeric fields present in training
NUMERIC_FIELDS = [
    "Patient Age",
    "Blood cell count (mcL)",
    "Mother's age",
    "Father's age",
    "No. of previous abortion",
    "White Blood cell count (thousand per microliter)",
]

# Order of target classes (we’ll read from the label encoder but keep this as reference)
VALID_CLASSES = [
    "Mitochondrial genetic inheritance disorders",
    "Multifactorial genetic inheritance disorders",
    "Single-gene inheritance diseases",
]

# ----------------------------------------------------
# Utilities
# ----------------------------------------------------
def _ensure_dir(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)

def load_model_package():
    """Lazy-load model package with cache."""
    global _CACHED_MODEL_PACKAGE
    if _CACHED_MODEL_PACKAGE is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model not found at: {MODEL_PATH}")
        pkg = joblib.load(MODEL_PATH)
        # Expecting: {'model': pipeline, 'label_encoder': ..., 'feature_names': [...]}
        if not all(k in pkg for k in ("model", "label_encoder", "feature_names")):
            raise ValueError("Model package is missing required keys: model, label_encoder, feature_names")
        _CACHED_MODEL_PACKAGE = pkg
    return _CACHED_MODEL_PACKAGE

def _norm_yes_no(v, yes="Yes", no="No", unk="Not available"):
    t = str(v).strip().lower()
    if t in ("y","yes","yeah","yep","true","1"): return yes
    if t in ("n","no","nope","false","0"): return no
    return unk

def _norm_birth_asphyxia(v):
    t = str(v).strip().lower()
    if t in ("y","yes","yeah","yep","true","1"): return "Yes"
    if t in ("n","no","nope","false","0"): return "No record"
    return "Not available"

def _norm_blood_test_result(v):
    t = str(v).strip().lower()
    if t in ("normal","ok","within range"): return "normal"
    if any(k in t for k in ("high","low","abnormal","slightly abnormal")):
        return "slightly abnormal"
    return "inconclusive"

def _norm_resp_rate(v):
    t = str(v).strip().lower()
    if "tachyp" in t: return "Tachypnea"
    if "normal" in t: return "Normal (30-60)"
    try:
        val = float(pd.to_numeric(v))
        return "Normal (30-60)" if 30 <= val <= 60 else "Tachypnea"
    except Exception:
        return "Normal (30-60)"

def _norm_heart_rate(v):
    t = str(v).strip().lower()
    if "tachy" in t: return "Tachycardia"
    if "normal" in t: return "Normal"
    try:
        val = float(pd.to_numeric(v))
        return "Tachycardia" if val > 100 else "Normal"
    except Exception:
        return "Normal"

def _coerce_float(v, default):
    try:
        x = float(pd.to_numeric(v))
        if np.isnan(x):
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def _coerce_int(v, default):
    try:
        x = int(round(float(pd.to_numeric(v))))
        return int(x)
    except Exception:
        return int(default)

def _build_input_row(user_data: dict, feature_names: list) -> pd.DataFrame:
    """
    Build a single-row DataFrame that matches the raw feature names the pipeline expects.
    Any missing fields are filled with safe defaults. Symptoms default to 0 unless provided.
    """
    # Start with everything missing
    row = {}

    # Numerics
    row["Patient Age"] = _coerce_int(user_data.get("Patient Age", user_data.get("age", 30)), 30)
    row["Blood cell count (mcL)"] = _coerce_float(user_data.get("Blood cell count (mcL)", 4.8), 4.8)
    row["Mother's age"] = _coerce_int(user_data.get("Mother's age", 30), 30)
    row["Father's age"] = _coerce_int(user_data.get("Father's age", 32), 32)
    row["No. of previous abortion"] = _coerce_int(user_data.get("No. of previous abortion", 0), 0)
    row["White Blood cell count (thousand per microliter)"] = _coerce_float(
        user_data.get("White Blood cell count (thousand per microliter)", 7.0),
        7.0
    )

    # Categoricals
    row["Gender"] = user_data.get("Gender", user_data.get("sex", "Ambiguous"))
    row["Birth asphyxia"] = _norm_birth_asphyxia(user_data.get("Birth asphyxia", "No record"))
    row["Autopsy shows birth defect (if applicable)"] = user_data.get(
        "Autopsy shows birth defect (if applicable)", user_data.get("Autopsy", "None")
    )
    row["Folic acid details (peri-conceptional)"] = _norm_yes_no(user_data.get("Folic acid details (peri-conceptional)", "No"), "Yes", "No", "Not available")
    row["H/O serious maternal illness"] = _norm_yes_no(user_data.get("H/O serious maternal illness", "No"), "Yes", "No", "Not available")
    row["H/O radiation exposure (x-ray)"] = _norm_yes_no(user_data.get("H/O radiation exposure (x-ray)", "No"), "Yes", "No", "Not available")
    row["H/O substance abuse"] = user_data.get("H/O substance abuse", "-")  # was present in training
    row["Assisted conception IVF/ART"] = _norm_yes_no(user_data.get("Assisted conception IVF/ART", "No"), "Yes", "No", "Not available")
    row["History of anomalies in previous pregnancies"] = _norm_yes_no(
        user_data.get("History of anomalies in previous pregnancies", "No"), "Yes", "No", "Not available"
    )
    row["Blood test result"] = _norm_blood_test_result(user_data.get("Blood test result", "normal"))
    row["Respiratory Rate (breaths/min)"] = _norm_resp_rate(user_data.get("Respiratory Rate (breaths/min)", "Normal (30-60)"))
    # NOTE: the training column name is missing a ')' in many datasets; use the exact name:
    row["Heart Rate (rates/min"] = _norm_heart_rate(user_data.get("Heart Rate (rates/min", "Normal"))

    # Gene inheritance flags (categoricals in training)
    row["Genes in mother's side"] = _norm_yes_no(user_data.get("Genes in mother's side", "No"), "Yes", "No", "Not available")
    row["Inherited from father"] = _norm_yes_no(user_data.get("Inherited from father", "No"), "Yes", "No", "Not available")
    # Maternal/Paternal gene are often binary strings
    row["Maternal gene"] = "Yes" if str(user_data.get("Maternal gene", "No")).strip().lower() not in ("no","none","nil","-","not detected","n/a","na","null","", "not sure","unknown") else "No"
    row["Paternal gene"] = "Yes" if str(user_data.get("Paternal gene", "No")).strip().lower() not in ("no","none","nil","-","not detected","n/a","na","null","", "not sure","unknown") else "No"

    # Symptoms: set 1/0 from list or direct flags
    selected = set(user_data.get("Symptoms", []))
    for s in SYMPTOM_COLUMNS:
        # allow either list OR direct scalar value
        if s in user_data:
            try:
                row[s] = int(user_data[s])
            except Exception:
                row[s] = 1 if str(user_data[s]).strip().lower() in ("1","yes","true","y") else 0
        else:
            row[s] = 1 if s in selected else 0

    # Build DataFrame with only the features the model expects (order does not matter)
    pkg = load_model_package()
    feat_names = list(pkg["feature_names"])
    # There might be a 'Disorder' column in training list; ignore if present
    safe_features = [f for f in feat_names if f != "Disorder"]
    # Fill any missing (unexpected) features with zeros
    for f in safe_features:
        if f not in row:
            # default: 0 for numeric-like, "Unknown" for cats, but encoder ignores unknowns; 0 is safe too
            row[f] = 0

    df = pd.DataFrame([row], columns=safe_features)
    return df

def _apply_domain_rules(row_dict: dict, base_probs: np.ndarray, class_names: list) -> np.ndarray:
    """
    Apply strong domain rules to override model predictions.
    If a strong rule fires, force high confidence (0.90/0.05/0.05).
    If no disorder symptoms are detected, balance probabilities evenly.
    """
    idx = {c: i for i, c in enumerate(class_names)}
    p = base_probs.copy()

    def g(name):  # get int flag for symptom
        return int(row_dict.get(name, 0))

    maternal_yes = str(row_dict.get("Genes in mother's side", "No")).lower().startswith("y") or \
                   str(row_dict.get("Maternal gene","No")).lower().startswith("y")
    paternal_yes = str(row_dict.get("Inherited from father", "No")).lower().startswith("y") or \
                   str(row_dict.get("Paternal gene","No")).lower().startswith("y")

    # Symptom clusters
    mito_syms = ["Lactic acidosis","Muscle weakness","Developmental delay","Seizures",
                 "Exercise intolerance","Eye movement abnormalities","Neuropathy",
                 "Movement disorders","Difficulty swallowing","Poor coordination","Tremors"]

    sg_syms = ["Cough","Wheezing","Frequent lung infections","Poor growth","Salty skin",
               "Shortness of breath","Digestive problems","Clubbing of fingers","Nasal polyps"]

    mf_syms = ["High blood sugar","Excessive thirst","Frequent urination",
               "Blurred vision","Slow healing","Weight loss","Increased hunger",
               "Fatigue","Joint pain","Heart problems"]

    mito_count = sum(g(s) for s in mito_syms)
    sg_count = sum(g(s) for s in sg_syms)
    mf_count = sum(g(s) for s in mf_syms)

    # Apply strong rules
    if maternal_yes and mito_count >= 3:
        p[:] = 0.05
        p[idx["Mitochondrial genetic inheritance disorders"]] = 0.90
        return p

    if paternal_yes and sg_count >= 3:
        p[:] = 0.05
        p[idx["Single-gene inheritance diseases"]] = 0.90
        return p

    if mf_count >= 4:
        p[:] = 0.05
        p[idx["Multifactorial genetic inheritance disorders"]] = 0.90
        return p

    # Neutral case (no disorder symptoms)
    if mito_count == 0 and sg_count == 0 and mf_count == 0:
        p[:] = 1.0 / len(class_names)  # spread evenly across all classes
        return p

    return p

def predict_disorder(user_data: dict):
    """
    Returns: (prediction_label, confidence_float_0to1, {label: prob})
    Adds a 'No Disorder / Low Risk' category if model confidence is spread evenly.
    """
    pkg = load_model_package()
    model = pkg["model"]
    le = pkg["label_encoder"]
    class_names = list(le.classes_)

    X = _build_input_row(user_data, pkg["feature_names"])
    base_probs = model.predict_proba(X)[0]

    # Build a plain dict row for rules
    row_dict = X.iloc[0].to_dict()
    adj_probs = _apply_domain_rules(row_dict, base_probs, class_names)

    top_idx = int(np.argmax(adj_probs))
    pred_label = class_names[top_idx]
    conf = float(adj_probs[top_idx])

    prob_map = {cls: float(adj_probs[i]) for i, cls in enumerate(class_names)}

    # Detect neutral / low-risk evenly spread case
    if all(abs(p - (1.0 / len(class_names))) < 0.05 for p in adj_probs):
        pred_label = "No Disorder / Low Risk"
        conf = 0.0  # Not confident in any disorder

    return pred_label, conf, prob_map

# Dictionary with explanations + recommendations for your 3 disorders
DISORDER_INFO = {
    "Mitochondrial genetic inheritance disorders": {
        "explanation": (
            "Mitochondrial genetic inheritance disorders are caused by mutations in the DNA of mitochondria, "
            "the energy-producing structures inside cells. Since mitochondria are passed from mother to child, "
            "these conditions are inherited maternally. They often affect energy-demanding organs like the brain, "
            "muscles, and heart, leading to fatigue, muscle weakness, and neurological problems."
        ),
        "recommendations": [
            "Consult a genetic counselor for family risk assessment.",
            "Follow a healthy lifestyle with a balanced diet and regular exercise, as tolerated.",
            "Avoid smoking and alcohol, which may worsen mitochondrial stress.",
            "Consider supplements (like Coenzyme Q10 or vitamins) if recommended by a doctor.",
            "Schedule regular check-ups to monitor heart, muscle, and neurological health."
        ],
    },
    "Multifactorial genetic inheritance disorders": {
        "explanation": (
            "Multifactorial genetic inheritance disorders are conditions caused by a combination of genetic factors "
            "and environmental influences. Examples include diabetes, heart disease, and certain cancers. "
            "These conditions usually run in families but are also strongly influenced by lifestyle and environment."
        ),
        "recommendations": [
            "Maintain a healthy diet and exercise regularly to lower risk factors.",
            "Go for regular health screenings (blood pressure, sugar levels, etc.).",
            "Avoid tobacco and limit alcohol intake.",
            "Stay aware of family medical history and discuss it with your healthcare provider.",
            "Adopt stress-reduction practices like yoga, meditation, or mindfulness."
        ],
    },
    "Single-gene inheritance disease": {
        "explanation": (
            "Single-gene inheritance diseases are caused by mutations in a single gene. "
            "These can be inherited in dominant, recessive, or X-linked patterns. Examples include cystic fibrosis, "
            "sickle cell anemia, and Huntington’s disease. Symptoms vary widely depending on the gene affected."
        ),
        "recommendations": [
            "Seek genetic testing to confirm the specific condition.",
            "Consult a genetic counselor for family planning advice.",
            "Follow treatment or therapy options prescribed for the specific disorder.",
            "Stay updated with ongoing research and support groups.",
            "Ensure regular follow-up with specialists for condition-specific monitoring."
        ],
    },
}

def _render_html_report(user_data: dict, pred_label: str, conf: float, prob_map: dict) -> str:
    """
    Generate a dynamic HTML report with compact spacing.
    """
    name = user_data.get("name", "")
    age = user_data.get("age", user_data.get("Patient Age", ""))
    sex = user_data.get("sex", user_data.get("Gender", ""))
    fam = user_data.get("family_history", user_data.get("Family History", ""))

    picked = [s for s in SYMPTOM_COLUMNS if int(user_data.get(s, 0)) == 1]
    symptoms_disp = ", ".join(picked) if picked else "None"

    prob_lines = "".join(
        f"<tr><td>{k}</td><td>{prob_map[k]*100:.2f}%</td></tr>" for k in prob_map
    )

    disorder_info = DISORDER_INFO.get(pred_label, {})
    pred_explanation = disorder_info.get("explanation", "No explanation available.")
    recommendations = disorder_info.get("recommendations", ["No specific recommendations available."])
    rec_html = "<ul>" + "".join(f"<li>{r}</li>" for r in recommendations) + "</ul>"

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GeneAccessAI - Genetic Risk Report</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 30px;
    font-size: 16px;
    line-height: 1.4;
    background-color: #f7f7f7;
    color: #333;
}}
h1 {{
    color: #667eea;
    font-size: 24px;
    text-align: center;
    margin-bottom: 6px;
    background-color: transparent;
}}
.disclaimer {{
    text-align: center;
    font-size: 13px;
    color: #555;
    margin-bottom: 15px;
    background-color: transparent;
}}
h2 {{
    color: #667eea;
    font-size: 18px;
    margin-top: 6px;
    margin-bottom: 6px;
}}
p, td, th {{
    font-size: 15px;
    margin: 4px 0;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
}}
table, th, td {{
    border: 1px solid #ccc;
}}
th, td {{
    padding: 6px 10px;
    text-align: left;
}}
th {{
    background-color: #a4b0e8;
}}
.section {{
    background-color: #fff;
    padding: 14px;
    margin-bottom: 14px;
    border-radius: 6px;
    box-shadow: 0 0 4px rgba(0,0,0,0.05);
}}
ul {{
    padding-left: 18px;
    margin: 4px 0;
}}
ul li {{
    margin-bottom: 2px;
}}
</style>
</head>
<body>

<h1>GeneAccessAI – Genetic Risk Report</h1>
<p class="disclaimer">
This report is generated for educational purposes only and <strong>does not constitute a medical diagnosis</strong>.
Clinical consultation is strongly recommended.
</p>

<div class="section">
<h2>1. Patient Details</h2>
<table>
<tr><th>Field</th><th>Information</th></tr>
<tr><td>Name</td><td>{name}</td></tr>
<tr><td>Age</td><td>{age}</td></tr>
<tr><td>Sex</td><td>{sex}</td></tr>
<tr><td>Family History</td><td>{fam}</td></tr>
<tr><td>Symptoms</td><td>{symptoms_disp}</td></tr>
</table>
</div>

<div class="section">
<h2>2. Report Summary</h2>
<p><strong>Prediction:</strong> {pred_label}</p>
<p><strong>Confidence Level:</strong> {conf*100:.2f}%</p>
<p><strong>Explanation</strong></p>
<p>{pred_explanation}</p>
</div>

<div class="section">
<h2>3. Prediction Probabilities</h2>
<table>
<tr><th>Disorder Type</th><th>Probability</th></tr>
{prob_lines}
</table>
</div>

<div class="section">
<h2>4. Recommendations</h2>
{rec_html}
</div>

<div class="section">
<h2>5. Report Metadata</h2>
<table>
<tr><th>Field</th><th>Information</th></tr>
<tr><td>Report Generated On</td><td>{datetime.now().strftime('%d %B %Y')}</td></tr>
<tr><td>Generated By</td><td>GeneAccessAI v1.0</td></tr>
</table>
</div>

</body>
</html>
"""
    return html

def _html_to_pdf(html: str, out_path: str) -> str:
    _ensure_dir(out_path)
    if XHTML2PDF_AVAILABLE:
        with open(out_path, "wb") as f:
            pisa.CreatePDF(html, dest=f)  # noqa
        return out_path
    # Fallback: save HTML if xhtml2pdf is not available
    alt = out_path.replace(".pdf", ".html")
    with open(alt, "w", encoding="utf-8") as f:
        f.write(html)
    return alt

def generate_custom_pdf_report(user_data: dict) -> str:
    """
    Generate the PDF (or HTML fallback) report and return the absolute path.
    """
    pred_label, conf, prob_map = predict_disorder(user_data)
    html = _render_html_report(user_data, pred_label, conf, prob_map)

    exports_dir = os.path.join(THIS_DIR, "exports")
    _ensure_dir(os.path.join(exports_dir, "dummy.pdf"))
    fname = f"geneaccess_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    out_path = os.path.abspath(os.path.join(exports_dir, fname))
    return _html_to_pdf(html, out_path)

