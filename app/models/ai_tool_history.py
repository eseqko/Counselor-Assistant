"""AI Tool generation history — stores past outputs for revisiting."""
from datetime import datetime
from app import db


class AIToolHistory(db.Model):
    __tablename__ = 'ai_tool_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tool_id = db.Column(db.String(80), nullable=False)
    tool_title = db.Column(db.String(200), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    inputs_json = db.Column(db.Text, nullable=False, default='{}')
    output_text = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='ai_tool_history')
    student = db.relationship('Student', backref='ai_tool_history')
