"""Generate synthetic HTML/text fixtures locally; never connects to Brevo."""
from pathlib import Path
from src.notification_email import render_html, render_text


def fixtures():
    first=dict(diga_id='acticore1',diga_name='ACTICORE1',detected_at='2026-09-17T12:00:00Z',
               change_type='new_diga',changed_field='entry',previous_value=None,new_value={'status':'provisional'})
    second=dict(first,diga_id='other',diga_name='DiGA mit einem besonders langen Namen für die mobile Darstellung',
                change_type='price_change', changed_field='pricing_information', previous_value='100 EUR', new_value='120 EUR')
    return {'one-new':[first], 'two-diga':[first,second],
            'multiple-events-one-diga':[first,dict(first,change_type='text_change')],
            'unknown':[dict(first,change_type='other_field_change')]}


def main():
    output=Path('work/email-previews')
    output.mkdir(parents=True,exist_ok=True)
    for name,events in fixtures().items():
        for extension,render in [('html',render_html),('txt',render_text)]:
            (output/f'{name}.{extension}').write_text(render(events,unsubscribe=True,
                impressum_url='https://example.invalid/impressum'),encoding='utf-8')
    print(f'Created {len(fixtures())} synthetic HTML/text fixtures in {output}. No email sent.')


if __name__=='__main__':
    main()
