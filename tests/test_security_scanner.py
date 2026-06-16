"""
Tests for the security scanner (project_mapper.core.security.scanner).

Verifies pattern detection, comment-line suppression, test-file severity
downgrade, and that the function never raises on unexpected input.
"""

from project_mapper.core.security.scanner import scan_file_security

# ── Baseline / no-op cases ────────────────────────────────────────────────────


def test_empty_content_returns_nothing():
    assert scan_file_security("app.py", "", "python") == []


def test_whitespace_only_returns_nothing():
    assert scan_file_security("app.py", "   \n  \t  \n", "python") == []


def test_unsupported_language_returns_nothing():
    code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
    assert scan_file_security("query.lua", code, "lua") == []


def test_never_raises_on_garbage_input():
    result = scan_file_security("???", "\x00\xff\xfe", "python")
    assert isinstance(result, list)


# ── Python SQL injection ───────────────────────────────────────────────────────


def test_python_sql_fstring_detected():
    code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
    findings = scan_file_security("app.py", code, "python")
    assert any(f.pattern_id == "py_sql_fstring" for f in findings)
    assert all(f.severity in ("critical", "high", "medium", "low") for f in findings)


def test_python_sql_concat_detected():
    code = 'db.execute("SELECT * FROM orders WHERE uid = " + user_id)'
    findings = scan_file_security("app.py", code, "python")
    assert any("sql" in f.pattern_id for f in findings)


def test_python_sql_format_detected():
    code = 'cursor.execute("SELECT * FROM t WHERE id = %s" % uid)'
    findings = scan_file_security("app.py", code, "python")
    assert any("sql" in f.pattern_id for f in findings)


# ── Python command injection ───────────────────────────────────────────────────


def test_python_eval_detected():
    code = "result = eval(user_input)"
    findings = scan_file_security("views.py", code, "python")
    assert any(f.pattern_id == "py_eval_exec" for f in findings)


def test_subprocess_shell_true_detected():
    code = "subprocess.Popen(cmd, shell=True)"
    findings = scan_file_security("runner.py", code, "python")
    assert any("subprocess" in f.pattern_id for f in findings)


# ── Comment-line suppression ───────────────────────────────────────────────────


def test_comment_line_not_flagged_hash():
    code = '# cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
    findings = scan_file_security("app.py", code, "python")
    assert findings == []


def test_comment_line_not_flagged_double_slash():
    code = "// db.query(`SELECT * FROM t WHERE id = ${uid}`)"
    findings = scan_file_security("app.js", code, "javascript")
    assert findings == []


# ── Test-file severity downgrade ───────────────────────────────────────────────


def test_critical_in_test_file_downgraded_to_high():
    code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
    prod_findings = scan_file_security("app.py", code, "python")
    test_findings = scan_file_security("tests/test_app.py", code, "python")

    prod_sev = next(f.severity for f in prod_findings if f.pattern_id == "py_sql_fstring")
    assert prod_sev == "critical"

    # In a test file the critical severity must be downgraded
    test_ids = [f.pattern_id for f in test_findings]
    if "py_sql_fstring" in test_ids:
        test_sev = next(f.severity for f in test_findings if f.pattern_id == "py_sql_fstring")
        assert test_sev != "critical"


def test_test_file_in_tests_dir_detected():
    code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
    findings = scan_file_security("tests/test_db.py", code, "python")
    # The scanner either downgrades or drops low-severity findings in test files
    # but should not crash, and any remaining severity must be non-critical
    for f in findings:
        assert f.severity != "critical"


# ── Finding metadata ───────────────────────────────────────────────────────────


def test_finding_has_owasp_category():
    code = 'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")'
    findings = scan_file_security("app.py", code, "python")
    assert findings
    assert all(f.owasp for f in findings)
    assert all("A0" in f.owasp for f in findings)


def test_finding_has_file_and_line():
    code = 'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")'
    findings = scan_file_security("src/db.py", code, "python")
    assert findings
    for f in findings:
        assert f.file == "src/db.py"
        assert isinstance(f.line, int)
        assert f.line >= 1


def test_findings_sorted_critical_first():
    code = "\n".join(
        [
            'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")',  # critical
            "subprocess.Popen(cmd, shell=True)",  # high
        ]
    )
    findings = scan_file_security("app.py", code, "python")
    if len(findings) >= 2:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for a, b in zip(findings, findings[1:]):
            assert order.get(a.severity, 9) <= order.get(b.severity, 9)


def test_to_dict_roundtrip():
    code = 'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")'
    findings = scan_file_security("app.py", code, "python")
    assert findings
    d = findings[0].to_dict()
    assert d["id"] == findings[0].pattern_id
    assert d["severity"] == findings[0].severity
    assert d["file"] == findings[0].file


# ── JavaScript patterns ───────────────────────────────────────────────────────


def test_js_sql_template_literal_detected():
    code = "db.query(`SELECT * FROM users WHERE id = ${userId}`)"
    findings = scan_file_security("api.js", code, "javascript")
    assert any("sql" in f.pattern_id for f in findings)


def test_js_eval_dynamic_detected():
    code = "eval(userInput)"
    findings = scan_file_security("app.js", code, "javascript")
    assert any("eval" in f.pattern_id for f in findings)
