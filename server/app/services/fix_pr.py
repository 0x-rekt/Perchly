"""Create a small, auditable GitHub PR for one reviewed finding."""

import re
import difflib
from dataclasses import dataclass
from typing import Any

from app.services.github_api import GENERATED_FIX_PR_MARKER, GitHubAppClient


class FixPrError(RuntimeError):
    """Raised when a finding cannot be converted into a safe fix PR."""


@dataclass(frozen=True)
class FixPrResult:
    url: str
    branch: str
    path: str


@dataclass(frozen=True)
class PatchFile:
    path: str
    before: str
    after: str
    diff: str


@dataclass(frozen=True)
class FixPatch:
    files: tuple[PatchFile, ...]
    diff: str


def apply_line_fix(content: str, *, line_start: int, line_end: int, suggested_fix: str) -> str:
    """Replace the finding's line range with its suggested code.

    This deliberately only supports a line-range replacement. It will never
    guess at a different file, search-and-replace unrelated text, or modify a
    file when the finding points outside its current contents.
    """
    if line_start < 1 or line_end < line_start:
        raise FixPrError("finding has an invalid line range")
    replacement = _suggested_code(suggested_fix)
    if not replacement.strip():
        raise FixPrError("finding does not contain an applicable suggested fix")
    newline = "\r\n" if "\r\n" in content else "\n"
    had_trailing_newline = content.endswith(("\n", "\r"))
    lines = content.splitlines()
    if line_end > len(lines):
        raise FixPrError("finding line range is outside the current file revision")
    replacement_lines = replacement.replace("\r\n", "\n").split("\n")
    updated = lines[: line_start - 1] + replacement_lines + lines[line_end:]
    result = newline.join(updated)
    return result + (newline if had_trailing_newline else "")


def _suggested_code(value: str) -> str:
    """Extract code from the fenced format used by model suggestions."""
    text = value.strip()
    blocks = re.findall(r"```(?:[A-Za-z0-9_+#.-]+)?\s*\n?(.*?)```", text, flags=re.S)
    if blocks:
        return blocks[0].strip("\r\n")
    return text


def build_patch(*, finding: dict[str, Any], repository_files: list[dict[str, Any]]) -> FixPatch:
    """Build a reviewable unified patch from a finding suggestion.

    Suggestions that contain a unified diff may change multiple files. Plain
    code suggestions are safely applied only to the finding's reported range.
    """
    suggested = finding.get("suggested_fix")
    path = finding.get("file")
    if not isinstance(suggested, str) or not suggested.strip():
        raise FixPrError("finding does not contain an applicable suggested fix")
    if not isinstance(path, str) or not _safe_path(path):
        raise FixPrError("finding does not point to a safe repository-relative file")
    contents = {
        value.get("path"): value.get("content")
        for value in repository_files
        if isinstance(value, dict) and isinstance(value.get("path"), str)
        and isinstance(value.get("content"), str)
    }
    if path not in contents:
        raise FixPrError("the reviewed file is not available for a safe preview")
    diff_text = _suggested_code(suggested)
    if "\n--- " in f"\n{diff_text}" and "\n+++ " in f"\n{diff_text}":
        files = _apply_unified_diff(diff_text, contents)
    else:
        before = contents[path]
        after = apply_line_fix(
            before,
            line_start=int(finding.get("line_start", 0)),
            line_end=int(finding.get("line_end", 0)),
            suggested_fix=suggested,
        )
        files = (_patch_file(path, before, after),)
    if not files or all(item.before == item.after for item in files):
        raise FixPrError("suggested fix would not change the repository")
    return FixPatch(files=files, diff="\n".join(item.diff for item in files))


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith(("/", "\\")) and "\\" not in path and ".." not in path.split("/")


def _patch_file(path: str, before: str, after: str) -> PatchFile:
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return PatchFile(path=path, before=before, after=after, diff=diff)


def _apply_unified_diff(text: str, contents: dict[str, str]) -> tuple[PatchFile, ...]:
    lines = text.replace("\r\n", "\n").splitlines(keepends=True)
    output: list[PatchFile] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue
        old_path = lines[index].strip().split("\t", 1)[0][4:]
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise FixPrError("malformed unified diff")
        new_path = lines[index].strip().split("\t", 1)[0][4:]
        path = new_path.removeprefix("b/")
        if old_path.endswith("/dev/null") or not _safe_path(path) or path not in contents:
            raise FixPrError(f"unified diff references an unavailable file: {path}")
        index += 1
        source = contents[path].splitlines(keepends=True)
        result: list[str] = []
        cursor = 0
        while index < len(lines) and not lines[index].startswith("--- "):
            if not lines[index].startswith("@@"):
                index += 1
                continue
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", lines[index])
            if not match:
                raise FixPrError("malformed unified diff hunk")
            target = int(match.group(1)) - 1
            result.extend(source[cursor:target])
            cursor = target
            index += 1
            while index < len(lines) and not lines[index].startswith(("@@", "--- ")):
                line = lines[index]
                index += 1
                if line.startswith(" "):
                    if cursor >= len(source) or source[cursor].rstrip("\r\n") != line[1:].rstrip("\r\n"):
                        raise FixPrError(f"unified diff context mismatch in {path}")
                    result.append(source[cursor]); cursor += 1
                elif line.startswith("-"):
                    if cursor >= len(source) or source[cursor].rstrip("\r\n") != line[1:].rstrip("\r\n"):
                        raise FixPrError(f"unified diff removal mismatch in {path}")
                    cursor += 1
                elif line.startswith("+"):
                    result.append(line[1:])
                elif line.startswith("\\"):
                    continue
                else:
                    raise FixPrError("malformed unified diff line")
        result.extend(source[cursor:])
        before = contents[path]
        after = "".join(result)
        output.append(_patch_file(path, before, after))
    if not output:
        raise FixPrError("suggested fix did not contain a unified diff")
    return tuple(output)


async def create_fix_pr(
    *,
    github: GitHubAppClient,
    repository: str,
    pr_number: int,
    head_sha: str,
    finding: dict[str, object],
    patch: FixPatch,
    installation_token: str,
) -> FixPrResult:
    short_id = str(finding.get("finding_id") or "finding")[:12]
    branch = f"perchly/fix/pr-{pr_number}-{short_id}"
    existing = await github.find_open_pull_request(
        repository=repository, head=branch, installation_token=installation_token
    )
    if existing:
        return FixPrResult(url=existing, branch=branch, path=patch.files[0].path)
    base = await github.pull_request_base_branch(
        repository=repository, pr_number=pr_number, installation_token=installation_token
    )
    await github.ensure_branch(
        repository=repository,
        branch=branch,
        from_sha=head_sha,
        installation_token=installation_token,
    )
    for patch_file in patch.files:
        file = await github.repository_file_version(
            repository=repository,
            path=patch_file.path,
            revision=head_sha,
            installation_token=installation_token,
        )
        if file.content != patch_file.before:
            raise FixPrError(f"{patch_file.path} changed since the preview was generated")
        await github.update_repository_file(
            repository=repository,
            path=patch_file.path,
            branch=branch,
            content=patch_file.after,
            file_sha=file.sha,
            message=f"fix: address Perchly finding in {patch_file.path}",
            installation_token=installation_token,
        )
    paths = ", ".join(item.path for item in patch.files)
    line_start = finding.get("line_start", "?")
    line_end = finding.get("line_end", "?")
    path = patch.files[0].path
    url = await github.create_pull_request(
        repository=repository,
        head=branch,
        base=base,
        title=f"fix: address Perchly finding in {path}",
        body=(
            f"{GENERATED_FIX_PR_MARKER}\n"
            f"This PR was generated by Perchly for review finding `{short_id}`.\n\n"
            f"**Files:** `{paths}`\n\n"
            f"**Location:** `{path}:{line_start}-{line_end}`\n\n"
            f"**Finding:** {finding.get('message', '')}\n\n"
            "Please review the generated change before merging."
        ),
        installation_token=installation_token,
    )
    return FixPrResult(url=url, branch=branch, path=path)
