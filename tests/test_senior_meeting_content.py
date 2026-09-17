"""The Senior / Post-Secondary meeting content bank is plain data with a
self-check; pin the invariants the meeting page relies on."""
from app.utils import senior_meeting_content as c


def test_content_validates_clean():
    assert c.validate() == []


def test_every_pathway_has_a_checklist_and_deadlines():
    for p in c.PATHWAYS:
        items = c.items_for_pathway(p)
        assert items, p
        assert all('all' in i['pathways'] or p in i['pathways'] for i in items)
        assert c.deadlines_for_pathway(p), p


def test_checklist_items_that_sync_the_plan_name_real_fields():
    synced = {i['key']: i['maps_to'] for i in c.CHECKLIST if i['maps_to']}
    assert synced['fafsa_submitted'] == ('fafsa_status', 'submitted')
    assert synced['cadaa_submitted'] == ('dream_act_status', 'submitted')
    assert synced['transcript_final_sent'] == ('transcript_sent', True)
    assert synced['personal_statement_final'] == ('personal_statement_status', 'final')


def test_question_bank_covers_both_meeting_types_and_every_sfbt_move():
    assert c.questions_for('scaling', 'first')
    assert c.questions_for('followup_visit', 'followup')
    assert not c.questions_for('followup_visit', 'first'), 'follow-up prompts only on return visits'
    tags = {t for q in c.QUESTIONS for t in q['framework']}
    for t in ('SFBT:scaling', 'SFBT:exception', 'SFBT:miracle', 'SFBT:coping',
              'SFBT:relationship', 'SFBT:compliment', 'SFBT:whats_better', 'SFBT:next_step'):
        assert t in tags, t
    for q in c.QUESTIONS:
        assert q['asca'] and all(code in c.ASCA_STANDARDS for code in q['asca']), q['key']
