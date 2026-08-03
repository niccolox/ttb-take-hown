"""Static 508 tripwires (audit F10): cheap assertions that keep the
accessibility posture from silently regressing. The dynamic pass is
axe-core in CI; the manual screen-reader session is a human step."""

from pathlib import Path

WEB = Path(__file__).parents[1] / "web"
HTML = (WEB / "index.html").read_text()
JS = (WEB / "app.js").read_text()


def test_document_basics():
    assert 'lang="en"' in HTML
    assert 'name="viewport"' in HTML
    assert "<title>" in HTML


def test_status_regions_announced():
    assert 'id="err" role="alert"' in HTML
    assert 'aria-live="polite"' in HTML          # progress/status line


def test_form_inputs_have_labels():
    import re
    for input_id in re.findall(r'<input[^>]*\bid="([^"]+)"', HTML):
        assert f'for="{input_id}"' in HTML, f"input #{input_id} lacks a label[for]"


def test_icon_only_buttons_carry_aria_labels():
    # per-field decision buttons and rotate buttons are icon-first — the
    # accessible name must come from aria-label, not the artwork
    assert 'aria-label="${v} — ${esc(FIELD_LABELS[f.field]' in JS
    assert 'aria-label", `Rotate the ${p.panel}' in JS
    assert 'aria-hidden="true"' in JS            # SVGs hidden from readers


def test_filters_expose_pressed_state():
    assert 'aria-pressed' in HTML and 'aria-pressed' in JS


def test_focus_restoration_present():
    assert "captureFocus" in JS and "restoreFocus" in JS
