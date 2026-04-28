"""District Knowledge Base utilities — extraction, chunking, and retrieval."""
import os
import re
from collections import Counter

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'text', 'md', 'docx'}

DOCUMENT_CATEGORIES = {
    'crisis_protocol': {'label': 'Crisis Protocol', 'icon': '&#128680;'},
    'handbook': {'label': 'School Handbook', 'icon': '&#128214;'},
    'graduation': {'label': 'Graduation Requirements', 'icon': '&#127891;'},
    'college': {'label': 'College & A-G Policy', 'icon': '&#127979;'},
    'referral': {'label': 'Referral Procedures', 'icon': '&#128203;'},
    'curriculum': {'label': 'Curriculum / Courses', 'icon': '&#128218;'},
    'sel': {'label': 'SEL / Mental Health', 'icon': '&#128154;'},
    'other': {'label': 'Other', 'icon': '&#128196;'},
}

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_file(filepath):
    """Extract text from a file. Returns (full_text, page_texts) where
    page_texts is a list of (page_number, text) tuples."""
    ext = filepath.rsplit('.', 1)[-1].lower()
    if ext == 'pdf':
        return _extract_pdf(filepath)
    elif ext == 'docx':
        return _extract_docx(filepath)
    elif ext in ('txt', 'text', 'md'):
        return _extract_text(filepath)
    return '', []


def _extract_pdf(filepath):
    from PyPDF2 import PdfReader
    reader = PdfReader(filepath)
    full_text = []
    page_texts = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ''
        text = text.strip()
        if text:
            full_text.append(text)
            page_texts.append((i + 1, text))
    return '\n\n'.join(full_text), page_texts


def _extract_docx(filepath):
    from docx import Document
    doc = Document(filepath)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full_text = '\n\n'.join(paragraphs)
    return full_text, [(1, full_text)]


def _extract_text(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read().strip()
    return text, [(1, text)]


def chunk_text(text, page_texts=None, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping word-based chunks.
    Returns list of dicts: {text, chunk_index, page_number}."""
    words = text.split()
    if not words:
        return []

    page_map = {}
    if page_texts:
        pos = 0
        for page_num, page_text in page_texts:
            page_words = page_text.split()
            for _ in page_words:
                if pos < len(words):
                    page_map[pos] = page_num
                    pos += 1

    chunks = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunk_text_str = ' '.join(chunk_words)
        page_num = page_map.get(start)

        chunks.append({
            'text': chunk_text_str,
            'chunk_index': idx,
            'page_number': page_num,
        })
        idx += 1
        if end >= len(words):
            break
        start = end - overlap

    return chunks


def _tokenize(text):
    """Simple word tokenization and lowering for search."""
    return re.findall(r'[a-z0-9]+', text.lower())


def search_chunks(query, chunks, top_k=5):
    """Keyword-based chunk retrieval using term frequency scoring.
    chunks: list of KnowledgeChunk ORM objects.
    Returns top_k most relevant chunks."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_counts = Counter(query_tokens)
    scored = []
    for chunk in chunks:
        chunk_tokens = _tokenize(chunk.text)
        chunk_counts = Counter(chunk_tokens)
        score = sum(query_counts[t] * chunk_counts.get(t, 0) for t in query_counts)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def build_knowledge_context(query, all_chunks, max_tokens=600):
    """Build a knowledge base context string for AI prompt injection.
    Retrieves the most relevant chunks, optimized for small local models."""
    relevant = search_chunks(query, all_chunks, top_k=3)
    if not relevant:
        return ''

    lines = ['\n--- DISTRICT KNOWLEDGE BASE ---']
    word_count = 0
    for chunk in relevant:
        chunk_words = chunk.text.split()
        if word_count + len(chunk_words) > max_tokens:
            break
        source = f' (Page {chunk.page_number})' if chunk.page_number else ''
        doc_name = chunk.document.original_filename if chunk.document else 'Unknown'
        lines.append(f'[From: {doc_name}{source}]')
        lines.append(chunk.text)
        lines.append('')
        word_count += len(chunk_words)

    lines.append('--- END KNOWLEDGE BASE ---\n')
    return '\n'.join(lines)
