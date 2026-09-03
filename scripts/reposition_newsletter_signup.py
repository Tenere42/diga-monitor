from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

old = '''    render_page_header()\n\n    real_events, scan_history = load_dashboard_data(\n'''
new = '''    render_page_header()\n    render_newsletter_signup_section()\n\n    real_events, scan_history = load_dashboard_data(\n'''
if old not in text:
    raise SystemExit("header anchor not found")
text = text.replace(old, new, 1)

text = text.replace('''        st.info("Keine echten Änderungen seit Tracking Beginn erkannt.")\n        render_newsletter_signup_section()\n        render_public_footer()\n''', '''        st.info("Keine echten Änderungen seit Tracking Beginn erkannt.")\n        render_public_footer()\n''')
text = text.replace('''    render_newsletter_signup_section()\n    render_public_footer()\n''', '''    render_public_footer()\n''', 1)

path.write_text(text, encoding="utf-8")
