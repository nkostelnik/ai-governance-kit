"""Optional web form: full flow against a real local server, extraction faked."""

import threading
from datetime import date
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest

from ai_governance.register import Register, ToolEntry, confirm_tool
from ai_governance.rubric import load_rubric
from webapp import App, fake_call, make_handler, memo_to_html

LOW_ANSWERS = [("data_sensitivity", "public"), ("personal_data", "no_personal_data"),
               ("decision_impact", "draft_reviewed"), ("regulated_domain", "no_regulated_domain"),
               ("audience", "personal_use"), ("accuracy_criticality", "errors_harmless")]


@pytest.fixture
def server(tmp_path):
    reg = tmp_path / "register"
    tool = confirm_tool(ToolEntry(id="assistant", name="Approved Assistant", vendor="Fictional",
                                  proposed_level="enterprise_zdr"),
                        "enterprise_zdr", "A. Counsel", "legal", load_rubric(), date(2026, 10, 10))
    Register(reg).save_tool(tool)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(reg, tmp_path / "out", call=fake_call)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", reg
    httpd.shutdown()


def get(url):
    with urlopen(url) as r:
        return r.read().decode("utf-8")


def post(url, pairs):
    try:
        with urlopen(url, data=urlencode(pairs).encode()) as r:   # follows the 303 to the result page
            return r.status, r.read().decode("utf-8")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_home_shows_disclaimer_and_registered_tools(server):
    base, _ = server
    page = get(base + "/")
    assert "Not legal advice" in page and "Approved Assistant" in page


def test_full_flow_request_answers_signoff(server):
    base, reg = server
    status, page = post(base + "/assess", [("description", "Brainstorm slogans for a public campaign."),
                                           ("tool", "assistant")])
    assert status == 200 and "UC-001" in page and "Open questions" in page and "provisional" in page

    status, page = post(base + "/use/UC-001/answer", LOW_ANSWERS)
    assert "awaiting signoff" in page and "Sign-off" in page
    assert Register(reg).use_case("UC-001").result.tier.value == "Low"

    status, page = post(base + "/use/UC-001/sign", [("role", "business_owner"), ("name", "B. Owner")])
    assert status == 200 and "approved" in page and "B. Owner" in page
    assert Register(reg).use_case("UC-001").status == "approved"
    assert "UC-001" in get(base + "/register")


def test_wrong_role_sign_is_refused_with_message(server):
    base, _ = server
    post(base + "/assess", [("description", "x"), ("tool", "assistant")])
    post(base + "/use/UC-001/answer", LOW_ANSWERS)
    status, page = post(base + "/use/UC-001/sign", [("role", "legal"), ("name", "Someone")])
    assert status == 400 and "not a required approver" in page


def test_user_text_is_escaped(server):
    base, _ = server
    status, page = post(base + "/assess", [("description", "<script>alert(1)</script> chatbot"), ("tool", "")])
    assert "<script>alert(1)</script>" not in page


def test_unknown_paths_are_404(server):
    base, _ = server
    for path in ["/use/../register", "/use/UC-999", "/nope"]:
        with pytest.raises(HTTPError) as e:
            get(base + path)
        assert e.value.code == 404


def test_memo_to_html_escapes_and_formats():
    out = memo_to_html("# Title <b>\n\n- **bold** item\n\n| A | B |\n|---|---|\n| <i>x</i> | y |\n")
    assert "<h2>Title &lt;b&gt;</h2>" in out
    assert "<li><strong>bold</strong> item</li>" in out
    assert "<td>&lt;i&gt;x&lt;/i&gt;</td>" in out
