from app.services.retrieval import SPECIALIST_QUERIES, chunk_changed_files


def test_chunk_changed_files_tracks_new_file_lines_and_paths() -> None:
    diff = """diff --git a/app/auth.py b/app/auth.py
index 111..222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,3 +10,5 @@ def login(user):
     validate(user)
+    token = issue_token(user)
+    return token
diff --git a/README.md b/README.md
index 333..444 100644
--- a/README.md
+++ b/README.md
@@ -2,1 +2,2 @@ Usage
 Run the app.
+Set DATABASE_URL before starting.
"""

    chunks = chunk_changed_files(diff)

    assert [(chunk.path, chunk.line_start, chunk.line_end) for chunk in chunks] == [
        ("app/auth.py", 10, 12),
        ("README.md", 2, 3),
    ]
    assert "token = issue_token(user)" in chunks[0].content
    assert "DATABASE_URL" in chunks[1].content


def test_retrieval_defines_one_query_for_each_specialist() -> None:
    assert set(SPECIALIST_QUERIES) == {
        "security",
        "quality",
        "test_coverage",
        "docs",
    }