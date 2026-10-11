"""Optional local intake web form. Python standard library only.

    python webapp.py                     # http://127.0.0.1:8765
    python webapp.py --fake-llm          # no API calls: every fact comes back unknown

Pages: a request form, the use case (follow-up questions as button-style
choices, then sign-off), and the register. It reuses the same functions as
assess.py and register.py; there is no separate logic here.

Local demo only. It binds to 127.0.0.1 and has no login, so anyone using the
page can sign as any role: the sign-off page illustrates the workflow and is
not a control. Synthetic data only. Requires attorney review; not legal advice.
"""

import argparse
from datetime import date
import html
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from ai_governance import DISCLAIMER, llm
from ai_governance.cli_helpers import next_use_case_id, write_outputs
from ai_governance.intake import Profile, ProfileField, RawExtraction, answer_follow_ups, run_intake
from ai_governance.memo import render_memo
from ai_governance.register import DEFAULT_REGISTER, Register, assess_use_case, sign_off
from ai_governance.rubric import load_rubric

ROOT = Path(__file__).resolve().parent
USE_ID = re.compile(r"UC-\d{3,}")

STYLE = """
:root { --bg: #fafaf8; --fg: #1d1d1b; --muted: #6b6b66; --line: #dcdcd6; --card: #ffffff;
        --accent: #2f5d8a; --accent-bg: #e8eff6; --warn: #8a4b0f; --warn-bg: #fbf0e3; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #1b1b1a; --fg: #ececea; --muted: #a3a39d; --line: #3a3a37; --card: #242422;
          --accent: #8fb6dc; --accent-bg: #23303c; --warn: #f0b47a; --warn-bg: #3a2c1e; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.6 system-ui, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; }
nav { display: flex; gap: 16px; margin-bottom: 8px; } nav a { color: var(--accent); }
.notice { background: var(--warn-bg); color: var(--warn); padding: 10px 14px; border-radius: 8px; font-size: 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 20px; margin: 16px 0; }
textarea, select, input[type=text] { width: 100%; font: inherit; padding: 8px; border: 1px solid var(--line);
  border-radius: 8px; background: var(--card); color: var(--fg); }
textarea { min-height: 140px; }
button { font: inherit; padding: 8px 18px; border-radius: 8px; border: 1px solid var(--accent);
  background: var(--accent); color: var(--card); cursor: pointer; }
.choices { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 16px; }
.choice input { position: absolute; opacity: 0; }
.choice span { display: inline-block; padding: 6px 12px; border: 1px solid var(--line); border-radius: 999px; cursor: pointer; font-size: 14px; }
.choice input:checked + span { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); }
.choice input:focus-visible + span { outline: 2px solid var(--accent); }
.tier { font-size: 22px; font-weight: 600; }
.error { color: var(--warn); font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 14px; display: block; overflow-x: auto; }
th, td { border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
blockquote { margin: 0; padding: 8px 12px; border-left: 3px solid var(--warn); background: var(--warn-bg); }
"""


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def inline(text: str) -> str:
    """Escape, then apply the two inline styles the memo uses: **bold** and `code`."""
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def memo_to_html(markdown: str) -> str:
    """Convert the memo's limited markdown (headings, bullets, tables, quote, rule) to HTML.
    Every piece of text is escaped first; nothing from the record is inserted raw."""
    out, table = [], []

    def flush_table():
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|(\s*-+\s*\|)+", r)]
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in cells[1:])
            head = "".join(f"<th>{inline(c)}</th>" for c in cells[0])
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            table.clear()

    in_list = False
    for line in markdown.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush_table()
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("## "):
            out.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("# "):
            out.append(f"<h2>{inline(line[2:])}</h2>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    flush_table()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def fake_call(system, user, output_format):
    """--fake-llm: no API call. Every fact comes back unknown, so every follow-up is asked."""
    profile = Profile(**{f: ProfileField(value=None, quote=None) for f in Profile.model_fields})
    profile.use_case_name = ProfileField(value="Web form request (fake extraction)", quote=None)
    return llm.LLMResult(parsed=RawExtraction(profile=profile, dimensions=[]), stop_reason="end_turn")


class App:
    def __init__(self, register_dir: Path, out_dir: Path, call=llm.parse):
        self.register, self.out_dir, self.call, self.rubric = Register(register_dir), out_dir, call, load_rubric()

    # ----- pages -----------------------------------------------------------------

    def page(self, title: str, body: str) -> str:
        return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
                f"<title>{esc(title)}</title><style>{STYLE}</style></head><body><main>"
                f"<nav><a href='/'>New request</a><a href='/register'>Register</a></nav>"
                f"<p class='notice'>{esc(DISCLAIMER)} Local demo: no login; synthetic data only.</p>"
                f"{body}</main></body></html>")

    def home(self, error: str = "") -> str:
        tools = sorted(p.stem for p in (self.register.root / "tools").glob("*.json"))
        options = "".join(f"<option value='{esc(t)}'>{esc(self.register.tool(t).name)}</option>" for t in tools)
        return self.page("New AI use request", f"""
          <h1>Propose an AI use</h1>
          {f"<p class='error'>{esc(error)}</p>" if error else ""}
          <form method='post' action='/assess' class='card'>
            <label for='description'><strong>What do you want to use AI for?</strong> Describe the data, who sees the
            output, and whether a person reviews it.</label>
            <textarea id='description' name='description' required></textarea>
            <p><label for='tool'><strong>Which tool?</strong></label>
            <select id='tool' name='tool'><option value=''>Not in the register (treated as unreviewed)</option>{options}</select></p>
            <button type='submit'>Assess (one Claude call, about $0.01)</button>
          </form>""")

    def use_case(self, use_id: str, error: str = "") -> str:
        entry = self.register.use_case(use_id)
        tool = self.register.tool(entry.tool_id) if entry.tool_id else None
        parts = [f"<h1>{esc(entry.id)}: {esc(entry.name)}</h1>",
                 f"<p class='error'>{esc(error)}</p>" if error else "",
                 f"<p class='tier'>{esc(entry.result.tier.value)} &middot; {esc(entry.status.replace('_', ' '))}</p>"]

        if entry.intake.follow_ups:
            groups = []
            for fu in entry.intake.follow_ups:
                choices = "".join(
                    f"<label class='choice'><input type='checkbox' name='{esc(fu.dimension_id)}' value='{esc(o.level_id)}'>"
                    f"<span>{esc(o.description)}</span></label>" for o in fu.options)
                groups.append(f"<fieldset><legend><strong>{esc(fu.question)}</strong></legend>"
                              f"<div class='choices'>{choices}</div></fieldset>")
            parts.append(f"<form method='post' action='/use/{esc(use_id)}/answer' class='card'>"
                         f"<h2>Open questions</h2><p>Select every option that applies. Leave a question blank to "
                         f"answer it later.</p>{''.join(groups)}<button type='submit'>Save answers</button></form>")

        if entry.status == "awaiting_signoff":
            roles = "".join(f"<option value='{esc(r)}'>{esc(self.rubric.approvers.catalog[r])}</option>"
                            for r in entry.missing_signers())
            parts.append(f"<form method='post' action='/use/{esc(use_id)}/sign' class='card'>"
                         f"<h2>Sign-off</h2><p>Still needed: {esc(', '.join(entry.missing_signers()))}. "
                         f"This page has no login, so it illustrates the workflow; it is not a control.</p>"
                         f"<p><label for='role'>Signing as</label><select id='role' name='role'>{roles}</select></p>"
                         f"<p><label for='name'>Name</label><input type='text' id='name' name='name' required></p>"
                         f"<button type='submit'>Sign</button></form>")

        parts.append(f"<div class='card'>{memo_to_html(render_memo(entry, tool, self.rubric))}</div>")
        return self.page(f"{entry.id} {entry.name}", "".join(parts))

    def register_page(self) -> str:
        rows = "".join(f"<tr><td><a href='/use/{esc(e.id)}'>{esc(e.id)}</a></td><td>{esc(e.name)}</td>"
                       f"<td>{esc(e.result.tier.value)}</td><td>{esc(e.status.replace('_', ' '))}</td>"
                       f"<td>{esc(e.next_review or '-')}</td></tr>" for e in self.register.use_cases())
        return self.page("AI register", "<h1>AI register</h1><table><thead><tr><th>Record</th><th>Use</th><th>Tier</th>"
                                        f"<th>Status</th><th>Next review</th></tr></thead><tbody>{rows}</tbody></table>")

    # ----- actions -----------------------------------------------------------------

    def save(self, entry):
        self.register.save_use_case(entry)
        tool = self.register.tool(entry.tool_id) if entry.tool_id else None
        write_outputs(self.out_dir, entry.id, render_memo(entry, tool, self.rubric), entry.model_dump_json(indent=2))

    def assess(self, form: dict) -> str:
        description = form.get("description", [""])[0].strip()
        if not description:
            raise ValueError("Please describe the proposed use.")
        tool_id = form.get("tool", [""])[0]
        tool = self.register.tool(tool_id) if tool_id else None
        intake = run_intake(description, self.rubric, call=self.call)
        entry = assess_use_case(next_use_case_id(self.register), intake, tool, "webapp", self.rubric)
        self.save(entry)
        return entry.id

    def answer(self, use_id: str, form: dict) -> None:
        entry = self.register.use_case(use_id)
        open_dims = {fu.dimension_id for fu in entry.intake.follow_ups}
        answers = {d: levels for d, levels in form.items() if d in open_dims and levels}
        if answers:
            intake = answer_follow_ups(entry.intake, answers, self.rubric)
            tool = self.register.tool(entry.tool_id) if entry.tool_id else None
            self.save(assess_use_case(entry.id, intake, tool, "webapp", self.rubric,
                                      strikes=entry.strikes, previous=entry))

    def sign(self, use_id: str, form: dict) -> None:
        name = form.get("name", [""])[0].strip()
        if not name:
            raise ValueError("Please enter the signer's name.")
        self.save(sign_off(self.register.use_case(use_id), form.get("role", [""])[0], name, date.today(), self.rubric))


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def send_html(self, body: str, status: int = 200):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def redirect(self, location: str):
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                return self.send_html(app.home())
            if path == "/register":
                return self.send_html(app.register_page())
            m = re.fullmatch(r"/use/(UC-\d{3,})", path)
            if m:
                try:
                    return self.send_html(app.use_case(m.group(1)))
                except FileNotFoundError:
                    pass
            self.send_html(app.page("Not found", "<h1>Not found</h1>"), 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            path = self.path.split("?")[0]
            if path == "/assess":
                try:
                    return self.redirect(f"/use/{app.assess(form)}")
                except (ValueError, FileNotFoundError) as e:
                    return self.send_html(app.home(str(e)), 400)
            m = re.fullmatch(r"/use/(UC-\d{3,})/(answer|sign)", path)
            if m:
                use_id, action = m.groups()
                try:
                    (app.answer if action == "answer" else app.sign)(use_id, form)
                    return self.redirect(f"/use/{use_id}")
                except (PermissionError, ValueError, KeyError) as e:
                    return self.send_html(app.use_case(use_id, str(e)), 400)
            self.send_html(app.page("Not found", "<h1>Not found</h1>"), 404)

        def log_message(self, *args):   # keep the console quiet
            pass

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local AI intake web form (demo).")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--register-dir", default=str(DEFAULT_REGISTER))
    parser.add_argument("--out-dir", default=str(ROOT / "output"))
    parser.add_argument("--fake-llm", action="store_true", help="no API calls; every fact comes back unknown")
    args = parser.parse_args(argv)
    app = App(Path(args.register_dir), Path(args.out_dir), call=fake_call if args.fake_llm else llm.parse)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    print(f"Serving on http://127.0.0.1:{args.port} (Ctrl+C to stop){' with fake extraction' if args.fake_llm else ''}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
