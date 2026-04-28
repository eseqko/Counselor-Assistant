"""IEP/504 Oversight — compliance date tracking and accommodation management."""
import os
from datetime import datetime, date, timezone
from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required, current_user
from app import db, csrf
from app.models.student import Student
from app.models.iep504 import IEP504Record

iep504_bp = Blueprint('iep504', __name__)

DOCS_DIR = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), '..', '..', 'data', 'iep504_docs')


# ── Page ──────────────────────────────────────────────────────────

@iep504_bp.route('/')
@login_required
def index():
    """Render the IEP/504 Oversight Kanban page."""
    return render_template('iep504/index.html')


# ── JSON API ──────────────────────────────────────────────────────

@iep504_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    """Return all IEP/504 records for the current counselor's caseload."""
    records = (IEP504Record.query
               .filter_by(counselor_id=current_user.id)
               .join(Student)
               .order_by(Student.last_name, Student.first_name)
               .all())
    return jsonify([r.to_dict() for r in records])


@iep504_bp.route('/api', methods=['POST'])
@csrf.exempt
@login_required
def api_create():
    """Create or update an IEP/504 record."""
    data = request.get_json(silent=True) or {}

    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'student_id is required'}), 400

    # Verify student is in counselor's caseload
    student = Student.query.filter_by(
        id=student_id,
        assigned_counselor_id=current_user.id
    ).first()
    if not student:
        return jsonify({'error': 'Student not found in your caseload'}), 404

    plan_type = data.get('plan_type', '').lower()
    if plan_type not in ('iep', '504'):
        return jsonify({'error': 'plan_type must be "iep" or "504"'}), 400

    # Upsert: update if record already exists for this student
    record = IEP504Record.query.filter_by(student_id=student_id).first()
    if record:
        record.plan_type = plan_type
        record.counselor_id = current_user.id
    else:
        record = IEP504Record(
            student_id=student_id,
            counselor_id=current_user.id,
            plan_type=plan_type,
        )
        db.session.add(record)

    if data.get('next_review_date'):
        record.next_review_date = date.fromisoformat(data['next_review_date'])
    if 'accommodations_text' in data:
        record.accommodations_text = data['accommodations_text'].strip()
    if 'notes' in data:
        record.notes = data['notes'].strip()

    record.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@iep504_bp.route('/api/<int:record_id>', methods=['PATCH'])
@csrf.exempt
@login_required
def api_update(record_id):
    """Update fields on an existing IEP/504 record."""
    record = IEP504Record.query.filter_by(
        id=record_id, counselor_id=current_user.id).first()
    if not record:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'plan_type' in data and data['plan_type'].lower() in ('iep', '504'):
        record.plan_type = data['plan_type'].lower()
    if 'next_review_date' in data:
        record.next_review_date = (
            date.fromisoformat(data['next_review_date'])
            if data['next_review_date'] else None)
    if 'accommodations_text' in data:
        record.accommodations_text = data['accommodations_text'].strip()
    if 'notes' in data:
        record.notes = data['notes'].strip()

    record.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(record.to_dict())


@iep504_bp.route('/api/<int:record_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def api_delete(record_id):
    """Delete an IEP/504 record."""
    record = IEP504Record.query.filter_by(
        id=record_id, counselor_id=current_user.id).first()
    if not record:
        return jsonify({'error': 'Not found'}), 404

    # Remove uploaded document if present (with path traversal check)
    if record.document_filename:
        path = os.path.join(DOCS_DIR, record.document_filename)
        if not os.path.abspath(path).startswith(os.path.abspath(DOCS_DIR)):
            path = None  # skip deletion if path is suspicious
        if path and os.path.exists(path):
            os.remove(path)

    db.session.delete(record)
    db.session.commit()
    return jsonify({'ok': True})


# ── PDF Upload & AI Parsing ───────────────────────────────────────

@iep504_bp.route('/api/<int:record_id>/upload', methods=['POST'])
@csrf.exempt
@login_required
def api_upload(record_id):
    """Upload an IEP at a Glance PDF for a record."""
    record = IEP504Record.query.filter_by(
        id=record_id, counselor_id=current_user.id).first()
    if not record:
        return jsonify({'error': 'Not found'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are accepted'}), 400

    os.makedirs(DOCS_DIR, exist_ok=True)

    # Remove old document if replacing
    if record.document_filename:
        old_path = os.path.join(DOCS_DIR, record.document_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    filename = f"iep504_{record.id}.pdf"
    file.save(os.path.join(DOCS_DIR, filename))
    record.document_filename = filename
    record.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'ok': True, 'filename': filename})


@iep504_bp.route('/api/<int:record_id>/parse', methods=['POST'])
@csrf.exempt
@login_required
def api_parse(record_id):
    """AI-parse an uploaded PDF to extract accommodations."""
    record = IEP504Record.query.filter_by(
        id=record_id, counselor_id=current_user.id).first()
    if not record:
        return jsonify({'error': 'Not found'}), 404

    if not record.document_filename:
        return jsonify({'error': 'No document uploaded yet'}), 400

    pdf_path = os.path.join(DOCS_DIR, record.document_filename)
    if not os.path.abspath(pdf_path).startswith(os.path.abspath(DOCS_DIR)):
        return jsonify({'error': 'Invalid document path'}), 400
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'Document file not found on disk'}), 404

    # Extract text from PDF
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    except ImportError:
        return jsonify({'error': 'PyPDF2 is not installed. Run: pip install PyPDF2'}), 500
    except Exception:
        return jsonify({'error': 'Failed to read PDF. The file may be corrupted.'}), 500

    if not text.strip():
        return jsonify({
            'error': 'Could not extract text from PDF. The document may be scanned/image-based.',
            'raw_text': '',
        }), 400

    # Send to Ollama for accommodation extraction
    from app.utils import ollama_client
    if not ollama_client.is_available():
        # Fallback: return raw text for manual editing
        return jsonify({
            'ok': True,
            'ai_available': False,
            'raw_text': text.strip(),
            'accommodations': '',
            'message': 'AI is not available. Raw PDF text provided for manual editing.',
        })

    prompt = (
        "Below is the text from a student's IEP at a Glance document. "
        "Extract ONLY the accommodations and modifications listed. "
        "Format each accommodation as a bullet point (- item). "
        "Do not include IEP goals, services, or other information. "
        "If no accommodations are found, say 'No accommodations found in document.'\n\n"
        f"--- DOCUMENT TEXT ---\n{text[:4000]}\n--- END ---"
    )
    system = (
        "You are a special education document parser. Extract accommodations "
        "accurately and concisely. Do not add commentary or explanations."
    )

    try:
        result = ollama_client.generate(prompt, system=system, temperature=0.2)
    except Exception as e:
        return jsonify({
            'ok': True,
            'ai_available': False,
            'raw_text': text.strip(),
            'accommodations': '',
            'message': 'AI processing failed. Raw text provided for manual editing.',
        })

    # Save extracted accommodations
    record.accommodations_text = result
    record.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'ok': True,
        'ai_available': True,
        'accommodations': result,
        'raw_text': text.strip(),
    })


@iep504_bp.route('/api/<int:record_id>/parse-stream', methods=['POST'])
@csrf.exempt
@login_required
def api_parse_stream(record_id):
    """Stream AI-parsed accommodations from an uploaded PDF."""
    import json as _json
    from flask import Response, stream_with_context
    from app.utils import ollama_client

    record = IEP504Record.query.filter_by(
        id=record_id, counselor_id=current_user.id).first()
    if not record:
        return jsonify({'error': 'Not found'}), 404

    if not record.document_filename:
        return jsonify({'error': 'No document uploaded yet'}), 400

    pdf_path = os.path.join(DOCS_DIR, record.document_filename)
    if not os.path.abspath(pdf_path).startswith(os.path.abspath(DOCS_DIR)):
        return jsonify({'error': 'Invalid document path'}), 400
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'Document file not found on disk'}), 404

    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    except ImportError:
        return jsonify({'error': 'PyPDF2 is not installed. Run: pip install PyPDF2'}), 500
    except Exception:
        return jsonify({'error': 'Failed to read PDF. The file may be corrupted.'}), 500

    if not text.strip():
        return jsonify({'error': 'Could not extract text from PDF.'}), 400

    if not ollama_client.is_available():
        return jsonify({
            'ok': True, 'ai_available': False, 'raw_text': text.strip(),
            'accommodations': '', 'message': 'AI is not available.',
        })

    prompt = (
        "Below is the text from a student's IEP at a Glance document. "
        "Extract ONLY the accommodations and modifications listed. "
        "Format each accommodation as a bullet point (- item). "
        "Do not include IEP goals, services, or other information. "
        "If no accommodations are found, say 'No accommodations found in document.'\n\n"
        f"--- DOCUMENT TEXT ---\n{text[:4000]}\n--- END ---"
    )
    system = (
        "You are a special education document parser. Extract accommodations "
        "accurately and concisely. Do not add commentary or explanations."
    )

    def generate():
        full_text = []
        try:
            for token, done in ollama_client.generate_stream(
                    prompt, system=system, temperature=0.2):
                full_text.append(token)
                if token:
                    yield f"data: {_json.dumps({'token': token})}\n\n"
                if done:
                    result_text = ''.join(full_text).strip()
                    record.accommodations_text = result_text
                    record.updated_at = datetime.now(timezone.utc)
                    db.session.commit()
                    yield f"data: {_json.dumps({'done': True, 'full_text': result_text, 'raw_text': text.strip()})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@iep504_bp.route('/api/<int:record_id>/document', methods=['GET'])
@login_required
def api_document(record_id):
    """Serve the uploaded PDF document."""
    record = IEP504Record.query.filter_by(
        id=record_id, counselor_id=current_user.id).first()
    if not record or not record.document_filename:
        return jsonify({'error': 'Not found'}), 404

    pdf_path = os.path.join(DOCS_DIR, record.document_filename)
    if not os.path.abspath(pdf_path).startswith(os.path.abspath(DOCS_DIR)):
        return jsonify({'error': 'Invalid document path'}), 400
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(pdf_path, mimetype='application/pdf')


# ── Student Search (IEP/504 students only) ────────────────────────

@iep504_bp.route('/api/students', methods=['GET'])
@login_required
def api_students():
    """Return students in caseload that have IEP or 504 flags set."""
    students = (Student.query
                .filter(
                    Student.assigned_counselor_id == current_user.id,
                    Student.status == 'active',
                    db.or_(
                        Student.iep_status == True,
                        Student.section_504 == True,
                    ))
                .order_by(Student.last_name, Student.first_name)
                .all())

    # Also check which already have records
    existing_ids = {r.student_id for r in
                    IEP504Record.query.filter_by(counselor_id=current_user.id).all()}

    return jsonify([
        {
            'id': s.id,
            'name': s.full_name,
            'display_name': s.display_name,
            'student_id_number': s.student_id_number,
            'grade_level': s.grade_level,
            'iep': s.iep_status,
            '504': s.section_504,
            'has_record': s.id in existing_ids,
        }
        for s in students
    ])
