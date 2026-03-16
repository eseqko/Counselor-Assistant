from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.glossary_term import GlossaryTerm

glossary_bp = Blueprint('glossary', __name__)


@glossary_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '')

    query = GlossaryTerm.query

    if search:
        query = query.filter(
            db.or_(
                GlossaryTerm.term.ilike(f'%{search}%'),
                GlossaryTerm.definition.ilike(f'%{search}%'),
            )
        )
    if category:
        query = query.filter_by(category=category)

    terms = query.order_by(GlossaryTerm.term).all()

    # Group by first letter
    grouped = {}
    for t in terms:
        letter = t.term[0].upper() if t.term else '#'
        grouped.setdefault(letter, []).append(t)

    return render_template('glossary/index.html',
        grouped=grouped, search=search, category=category,
        categories=GlossaryTerm.CATEGORIES)


@glossary_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_term():
    if request.method == 'POST':
        term = GlossaryTerm(
            term=request.form['term'],
            definition=request.form['definition'],
            category=request.form.get('category', ''),
            related_terms=request.form.get('related_terms', ''),
            source=request.form.get('source', ''),
        )
        db.session.add(term)
        db.session.commit()
        flash(f'Term "{term.term}" added.', 'success')
        return redirect(url_for('glossary.index'))

    return render_template('glossary/add.html', categories=GlossaryTerm.CATEGORIES)


@glossary_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_term(id):
    term = GlossaryTerm.query.get_or_404(id)

    if request.method == 'POST':
        term.term = request.form['term']
        term.definition = request.form['definition']
        term.category = request.form.get('category', '')
        term.related_terms = request.form.get('related_terms', '')
        term.source = request.form.get('source', '')
        db.session.commit()
        flash('Term updated.', 'success')
        return redirect(url_for('glossary.index'))

    return render_template('glossary/edit.html', term=term,
        categories=GlossaryTerm.CATEGORIES)


@glossary_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_term(id):
    term = GlossaryTerm.query.get_or_404(id)
    db.session.delete(term)
    db.session.commit()
    flash('Term deleted.', 'warning')
    return redirect(url_for('glossary.index'))


@glossary_bp.route('/seed', methods=['POST'])
@login_required
def seed_glossary():
    """Seed with common ASCA terms."""
    if GlossaryTerm.query.count() > 0:
        flash('Glossary already has entries.', 'info')
        return redirect(url_for('glossary.index'))

    terms = [
        ('ASCA National Model', 'A framework for school counseling programs that defines the school counselor\'s role in supporting student achievement, attendance, and discipline.', 'asca_model'),
        ('Direct Student Services', 'Services that require the school counselor to interact directly with students, including instruction, appraisal, and advisement.', 'asca_model'),
        ('Indirect Student Services', 'Services provided on behalf of students through consultation, collaboration, and referrals with parents, teachers, and community resources.', 'asca_model'),
        ('School Counseling Core Curriculum', 'Structured lessons designed to help students attain the desired competencies and to provide all students with the knowledge and skills appropriate for their developmental level.', 'asca_model'),
        ('Individual Student Planning', 'Activities that help all students plan, monitor, and manage their own learning as well as their personal and career development.', 'asca_model'),
        ('Responsive Services', 'Activities that address students\' immediate needs and concerns through counseling, crisis response, referrals, consultation, and peer facilitation.', 'asca_model'),
        ('SMART Goals', 'Goals that are Specific, Measurable, Attainable, Results-oriented, and Time-bound, used in school counseling program planning.', 'assessment'),
        ('Mindsets & Behaviors', 'ASCA standards for student success that describe the knowledge, skills, and attitudes students need to achieve academic success, career readiness, and social/emotional development.', 'asca_model'),
        ('Use-of-Time Assessment', 'An analysis of how school counselors spend their time across the four components: direct services, indirect services, program management, and non-counseling tasks.', 'asca_model'),
        ('RAMP', 'Recognized ASCA Model Program - a designation awarded to schools that align their school counseling program with the ASCA National Model.', 'asca_model'),
        ('504 Plan', 'A plan developed to ensure that a child with a disability receives accommodations that ensure academic success and access to the learning environment.', 'special_ed'),
        ('IEP', 'Individualized Education Program - a document developed for each public school child who needs special education, describing the child\'s learning needs and the services the school will provide.', 'special_ed'),
        ('FERPA', 'Family Educational Rights and Privacy Act - a federal law that protects the privacy of student education records.', 'ethics'),
        ('Mandated Reporter', 'A professional required by law to report suspected child abuse or neglect to appropriate authorities.', 'ethics'),
        ('Threat Assessment', 'A structured process to evaluate the potential that a student may carry out a threat of violence.', 'crisis'),
        ('Suicide Risk Assessment', 'A structured evaluation to determine if a student is at risk for suicide and to plan appropriate intervention.', 'crisis'),
        ('Safety Plan', 'A written document created collaboratively with a student in crisis that outlines coping strategies and resources for managing suicidal thoughts.', 'crisis'),
        ('College Readiness', 'The level of preparation a student needs to enroll and succeed in a credit-bearing course at a postsecondary institution without remediation.', 'college_readiness'),
        ('Career Development', 'The process through which individuals come to understand themselves as they relate to the world of work and their role in it.', 'career'),
        ('Social-Emotional Learning (SEL)', 'The process through which individuals acquire and apply knowledge, skills, and attitudes to develop healthy identities, manage emotions, achieve goals, show empathy, maintain relationships, and make responsible decisions.', 'social_emotional'),
    ]

    for term_name, definition, category in terms:
        t = GlossaryTerm(term=term_name, definition=definition,
                        category=category, source='ASCA National Model')
        db.session.add(t)

    db.session.commit()
    flash(f'Seeded {len(terms)} glossary terms.', 'success')
    return redirect(url_for('glossary.index'))
