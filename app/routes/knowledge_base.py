"""District Knowledge Base routes — upload, view, and manage documents."""
import os
import uuid
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, jsonify)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.knowledge_base import KnowledgeDocument, KnowledgeChunk
from app.utils.knowledge_base import (
    DOCUMENT_CATEGORIES, allowed_file, extract_text_from_file, chunk_text,
)
from app.utils.audit import log_action

kb_bp = Blueprint('knowledge_base', __name__, template_folder='../templates/knowledge_base')

KB_UPLOAD_DIR = 'knowledge_base'


def _kb_upload_path():
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], KB_UPLOAD_DIR)
    os.makedirs(path, exist_ok=True)
    return path


@kb_bp.route('/')
@login_required
def index():
    category = request.args.get('category', '')
    query = KnowledgeDocument.query.filter_by(user_id=current_user.id)
    if category:
        query = query.filter_by(category=category)
    docs = query.order_by(KnowledgeDocument.created_at.desc()).all()
    return render_template('knowledge_base/index.html',
                           documents=docs,
                           categories=DOCUMENT_CATEGORIES,
                           active_category=category)


@kb_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            flash('Please select a file.', 'error')
            return redirect(url_for('knowledge_base.upload'))

        if not allowed_file(file.filename):
            flash('Unsupported file type. Allowed: PDF, DOCX, TXT, MD', 'error')
            return redirect(url_for('knowledge_base.upload'))

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit('.', 1)[-1].lower()
        stored_name = f'{uuid.uuid4().hex}.{ext}'
        filepath = os.path.join(_kb_upload_path(), stored_name)
        file.save(filepath)

        file_size = os.path.getsize(filepath)
        category = request.form.get('category', 'other')
        description = request.form.get('description', '').strip()

        try:
            full_text, page_texts = extract_text_from_file(filepath)
        except Exception as e:
            os.remove(filepath)
            flash(f'Failed to extract text: {e}', 'error')
            return redirect(url_for('knowledge_base.upload'))

        if not full_text.strip():
            os.remove(filepath)
            flash('No text could be extracted from this file. It may be image-only.', 'error')
            return redirect(url_for('knowledge_base.upload'))

        chunks = chunk_text(full_text, page_texts)

        doc = KnowledgeDocument(
            user_id=current_user.id,
            filename=stored_name,
            original_filename=original_name,
            file_type=ext,
            file_size=file_size,
            category=category,
            description=description,
            page_count=len(page_texts),
            chunk_count=len(chunks),
        )
        db.session.add(doc)
        db.session.flush()

        for c in chunks:
            db.session.add(KnowledgeChunk(
                document_id=doc.id,
                chunk_index=c['chunk_index'],
                text=c['text'],
                page_number=c['page_number'],
            ))

        db.session.commit()
        log_action('knowledge_upload', 'knowledge_document', doc.id,
                   f'Uploaded: {original_name} ({len(chunks)} chunks)')
        flash(f'Uploaded "{original_name}" — {len(chunks)} chunks extracted.', 'success')
        return redirect(url_for('knowledge_base.document', doc_id=doc.id))

    return render_template('knowledge_base/upload.html',
                           categories=DOCUMENT_CATEGORIES)


@kb_bp.route('/document/<int:doc_id>')
@login_required
def document(doc_id):
    doc = KnowledgeDocument.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('knowledge_base.index'))
    chunks = doc.chunks.order_by(KnowledgeChunk.chunk_index).all()
    return render_template('knowledge_base/document.html',
                           doc=doc,
                           chunks=chunks,
                           categories=DOCUMENT_CATEGORIES)


@kb_bp.route('/document/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete(doc_id):
    doc = KnowledgeDocument.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('knowledge_base.index'))

    filepath = os.path.join(_kb_upload_path(), doc.filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    name = doc.original_filename
    db.session.delete(doc)
    db.session.commit()
    log_action('knowledge_delete', 'knowledge_document', doc_id,
               f'Deleted: {name}')
    flash(f'Deleted "{name}".', 'success')
    return redirect(url_for('knowledge_base.index'))


@kb_bp.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'chunks': []})

    from app.utils.knowledge_base import search_chunks
    all_chunks = KnowledgeChunk.query.join(KnowledgeDocument).filter(
        KnowledgeDocument.user_id == current_user.id
    ).all()
    results = search_chunks(q, all_chunks, top_k=10)
    return jsonify({'chunks': [
        {
            'text': c.text,
            'page_number': c.page_number,
            'document': c.document.original_filename,
            'category': c.document.category,
        }
        for c in results
    ]})
