import pytest

from app.services.fix_pr import FixPrError, apply_line_fix, build_patch


def test_apply_line_fix_replaces_only_finding_range():
    source = "one\ntwo\nthree\n"
    assert apply_line_fix(source, line_start=2, line_end=2, suggested_fix="```py\nTWO\n```") == (
        "one\nTWO\nthree\n"
    )


def test_apply_line_fix_rejects_out_of_range_and_empty_suggestion():
    with pytest.raises(FixPrError):
        apply_line_fix("one\n", line_start=2, line_end=2, suggested_fix="two")
    with pytest.raises(FixPrError):
        apply_line_fix("one\n", line_start=1, line_end=1, suggested_fix="   ")


def test_build_patch_accepts_a_multi_file_unified_diff():
    finding = {
        "file": "a.py", "line_start": 1, "line_end": 1,
        "suggested_fix": (
            "```diff\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
            "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-before\n+after\n```"
        ),
    }
    patch = build_patch(finding=finding, repository_files=[
        {"path": "a.py", "content": "old\n"},
        {"path": "b.py", "content": "before\n"},
    ])
    assert [item.path for item in patch.files] == ["a.py", "b.py"]
    assert "+++ b/b.py" in patch.diff
