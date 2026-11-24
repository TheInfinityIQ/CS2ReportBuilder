"""Render reviewed situation lessons with their exact frozen round records."""
from html import escape


def desk(snapshot, coaching):
    records = {r['id']:r for g in snapshot['games'] for r in g['rounds']}
    review = coaching.get('situation_review')
    if not review:
        return ''
    rows = []
    for item in review['dispositions']:
        if item['round_id'] not in records:
            raise ValueError('Reviewed supporting round is outside the frozen selection.')
        r = records[item['round_id']]
        rows.append(f'<tr><td>{escape(r["map"].removeprefix("de_").title())} R{r["round"]}<br><code>{escape(r["id"])}</code></td><td>{escape(item["decision"])}</td><td>{escape(item["limit"])}</td></tr>')
    return ('<h3>Eight-sequence evidence review</h3><p>These selected post-plant and last-alive examples remain supporting evidence. Their narrow scope does not establish recurring cross-map themes, so their lessons are withheld from the main narrative. This is not a frequency estimate or an independent native replay validation.</p>'
            '<div class="table-scroll"><table><thead><tr><th>Round</th><th>Use in the coaching</th><th>Interpretation boundary</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>')


def render(snapshot, coaching):
    by_id = {r['id']: r for g in snapshot['games'] for r in g['rounds']}
    lessons = coaching.get('situation_insights', [])
    reviewed = []
    positive, development = [], []
    for lesson in lessons:
        if lesson.get('review_status') != 'approved_bounded_lesson' or not lesson.get('review_response'):
            raise ValueError('Situation lesson has no recorded editorial approval.')
        if lesson.get('publication_scope') != 'cross_map_theme':
            raise ValueError('Individual illustrations belong in evidence, not the main narrative.')
        references = []
        for ref in lesson['references']:
            if ref['round_id'] not in by_id:
                raise ValueError('Situation reference is outside the frozen eligible selection.')
            record = by_id[ref['round_id']]
            if not record['start'] <= ref['anchor_tick'] <= record['end']:
                raise ValueError('Situation anchor is outside its recorded round.')
            references.append(dict(ref, record=record))
        if not references:
            raise ValueError('Situation lesson requires recorded evidence.')
        if len({r['record']['map'] for r in references}) < 2:
            raise ValueError('A cross-map theme requires evidence from different maps.')
        reviewed.append(dict(lesson, references=references))
        refs = f'{len({r["record"]["map"] for r in references})} maps represented'
        block = (f'<article class="situation-insight {escape(lesson["kind"])}" data-situation="{escape(lesson["id"])}">'
                 f'<span class="section-label">{escape(lesson["label"])}</span>'
                 f'<h3>{escape(lesson["heading"])}</h3><p>{escape(lesson["observation"])}</p>'
                 f'<p class="insight-meaning">{escape(lesson["meaning"])}</p>'
                 f'<div class="reading-cue"><span>TAKE INTO YOUR NEXT MATCH</span><p>{escape(lesson["cue"])}</p></div>'
                 f'<p class="reading-limit">{escape(lesson["limit"])}</p>'
                 f'<p class="evidence-caption">{refs} · individual anchors in the Analyst Desk</p></article>')
        (positive if lesson['kind']=='positive' else development).append(block)
    return ''.join(positive), ''.join(development), reviewed
