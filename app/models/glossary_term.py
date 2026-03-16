from app import db
from datetime import datetime, timezone


class GlossaryTerm(db.Model):
    """ASCA-aligned glossary of counseling topics and terms."""
    __tablename__ = 'glossary_terms'

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(200), unique=True, nullable=False)
    definition = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))
    related_terms = db.Column(db.Text)  # Comma-separated related term names
    source = db.Column(db.String(200))  # e.g., "ASCA National Model"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    CATEGORIES = [
        ('asca_model', 'ASCA National Model'),
        ('academic', 'Academic Development'),
        ('career', 'Career Development'),
        ('social_emotional', 'Social/Emotional Development'),
        ('assessment', 'Assessment & Data'),
        ('ethics', 'Ethics & Legal'),
        ('crisis', 'Crisis & Safety'),
        ('special_ed', 'Special Education'),
        ('college_readiness', 'College Readiness'),
        ('general', 'General Counseling'),
    ]
