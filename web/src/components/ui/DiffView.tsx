import { useMemo, useState } from "react";
import { Check, ChevronDown, Copy } from "../../lib/icons";

type RowKind = "context" | "add" | "del" | "meta";

type DiffRow = {
  kind: RowKind;
  oldNo: number | null;
  newNo: number | null;
  text: string;
};

type DiffHunk = {
  header: string;
  rows: DiffRow[];
};

export type DiffFile = {
  key: string;
  path: string;
  dir: string;
  base: string;
  additions: number;
  deletions: number;
  binary: boolean;
  hunks: DiffHunk[];
};

type SplitRow =
  | { kind: "pair"; left: DiffRow | null; right: DiffRow | null }
  | { kind: "meta"; row: DiffRow };

const stripPath = (value: string) => value.replace(/^[ab]\//, "");

function applyPaths(file: DiffFile, oldPath: string, newPath: string, index: number) {
  const shown = stripPath(newPath && newPath !== "/dev/null" ? newPath : oldPath);
  const slash = shown.lastIndexOf("/");
  file.path = shown;
  file.dir = slash >= 0 ? shown.slice(0, slash + 1) : "";
  file.base = slash >= 0 ? shown.slice(slash + 1) : shown;
  file.key = `${index}:${shown}`;
}

function parseDiff(diff: string): DiffFile[] {
  const lines = diff.replace(/\r\n/g, "\n").split("\n");
  const files: DiffFile[] = [];
  let file: DiffFile | null = null;
  let hunk: DiffHunk | null = null;
  let sawHeader = false;
  let oldNo = 0;
  let newNo = 0;
  let oldLeft = 0;
  let newLeft = 0;

  const createFile = (oldPath: string, newPath: string): DiffFile => {
    const next: DiffFile = {
      key: "",
      path: "",
      dir: "",
      base: "",
      additions: 0,
      deletions: 0,
      binary: false,
      hunks: [],
    };
    files.push(next);
    applyPaths(next, oldPath, newPath, files.length - 1);
    return next;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];

    if (hunk && line.startsWith("\\")) {
      hunk.rows.push({
        kind: "meta",
        oldNo: null,
        newNo: null,
        text: line,
      });
      continue;
    }

    if (hunk && file && (oldLeft > 0 || newLeft > 0)) {
      const marker = line[0];
      if (marker === "+") {
        hunk.rows.push({ kind: "add", oldNo: null, newNo, text: line.slice(1) });
        newNo += 1;
        newLeft -= 1;
        file.additions += 1;
        continue;
      }
      if (marker === "-") {
        hunk.rows.push({ kind: "del", oldNo, newNo: null, text: line.slice(1) });
        oldNo += 1;
        oldLeft -= 1;
        file.deletions += 1;
        continue;
      }
      if (marker === " " || line === "") {
        hunk.rows.push({
          kind: "context",
          oldNo,
          newNo,
          text: line === "" ? "" : line.slice(1),
        });
        oldNo += 1;
        newNo += 1;
        oldLeft -= 1;
        newLeft -= 1;
        continue;
      }
      hunk = null;
      oldLeft = 0;
      newLeft = 0;
    }

    if (line.startsWith("diff --git ")) {
      const match = /^diff --git a\/(.+) b\/(.+)$/.exec(line);
      file = createFile(
        match ? `a/${match[1]}` : "",
        match ? `b/${match[2]}` : line.slice(11),
      );
      hunk = null;
      sawHeader = false;
      continue;
    }
    if (line.startsWith("--- ")) {
      const oldPath = line.slice(4).split("\t")[0].trim();
      const nextLine = lines[index + 1] ?? "";
      const newPath = nextLine.startsWith("+++ ")
        ? nextLine.slice(4).split("\t")[0].trim()
        : "";
      if (nextLine.startsWith("+++ ")) index += 1;
      if (file && !sawHeader && file.hunks.length === 0 && !file.binary) {
        applyPaths(file, oldPath, newPath, files.length - 1);
      } else {
        file = createFile(oldPath, newPath);
      }
      hunk = null;
      sawHeader = true;
      continue;
    }
    if (line.startsWith("Binary files ") || line.startsWith("GIT binary patch")) {
      if (file) file.binary = true;
      hunk = null;
      continue;
    }
    const header = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/.exec(line);
    if (header) {
      if (!file) {
        file = createFile("", "");
      }
      sawHeader = true;
      oldNo = Number(header[1]);
      oldLeft = header[2] === undefined ? 1 : Number(header[2]);
      newNo = Number(header[3]);
      newLeft = header[4] === undefined ? 1 : Number(header[4]);
      hunk = { header: line, rows: [] };
      file.hunks.push(hunk);
      continue;
    }
  }

  return files;
}

function diffTotals(files: DiffFile[]) {
  return files.reduce(
    (totals, file) => ({
      additions: totals.additions + file.additions,
      deletions: totals.deletions + file.deletions,
    }),
    { additions: 0, deletions: 0 },
  );
}

function toSplitRows(rows: DiffRow[]): SplitRow[] {
  const paired: SplitRow[] = [];
  let index = 0;
  while (index < rows.length) {
    const row = rows[index];
    if (row.kind === "meta") {
      paired.push({ kind: "meta", row });
      index += 1;
      continue;
    }
    if (row.kind === "context") {
      paired.push({ kind: "pair", left: row, right: row });
      index += 1;
      continue;
    }
    const dels: DiffRow[] = [];
    const adds: DiffRow[] = [];
    while (index < rows.length && rows[index].kind !== "context" && rows[index].kind !== "meta") {
      if (rows[index].kind === "del") dels.push(rows[index]);
      else adds.push(rows[index]);
      index += 1;
    }
    const length = Math.max(dels.length, adds.length);
    for (let offset = 0; offset < length; offset += 1) {
      paired.push({ kind: "pair", left: dels[offset] ?? null, right: adds[offset] ?? null });
    }
  }
  return paired;
}

const GUTTER =
  "w-11 shrink-0 select-none border-r border-line/50 px-2 text-right font-mono text-[11px] leading-5 tabular-nums";

function UnifiedRow({ row }: { row: DiffRow }) {
  if (row.kind === "meta") {
    return (
      <div className="flex w-max min-w-full bg-canvas">
        <span className="w-[108px] shrink-0" />
        <code className="whitespace-pre px-3 font-mono text-[11px] leading-5 text-faint italic">
          {row.text}
        </code>
      </div>
    );
  }
  if (row.kind === "context") {
    return (
      <div className="group/row flex w-max min-w-full hover:bg-panel-2">
        <div className="sticky left-0 z-10 flex shrink-0 bg-canvas group-hover/row:bg-panel-2">
          <span className={`${GUTTER} text-faint`}>{row.oldNo}</span>
          <span className={`${GUTTER} text-faint`}>{row.newNo}</span>
          <span className="w-5 shrink-0" />
        </div>
        <code className="whitespace-pre px-3 font-mono text-[12px] leading-5 text-ink [tab-size:4]">
          {row.text}
        </code>
        <span className="min-w-3 flex-1" />
      </div>
    );
  }
  const added = row.kind === "add";
  return (
    <div
      className={`group/row flex w-max min-w-full ${
        added ? "bg-add-bg hover:bg-add-bg-hover" : "bg-del-bg hover:bg-del-bg-hover"
      }`}
    >
      <div
        className={`sticky left-0 z-10 flex shrink-0 ${
          added
            ? "bg-add-bg group-hover/row:bg-add-bg-hover"
            : "bg-del-bg group-hover/row:bg-del-bg-hover"
        }`}
      >
        <span className={`${GUTTER} text-muted`}>{added ? null : row.oldNo}</span>
        <span className={`${GUTTER} text-muted`}>{added ? row.newNo : null}</span>
        <span
          className={`w-5 shrink-0 text-center font-mono text-[12px] leading-5 ${
            added ? "text-add" : "text-del"
          }`}
        >
          {added ? "+" : "−"}
        </span>
      </div>
      <code className="whitespace-pre px-3 font-mono text-[12px] leading-5 text-ink [tab-size:4]">
        {row.text}
      </code>
      <span className="min-w-3 flex-1" />
    </div>
  );
}

function SplitSide({ row, side }: { row: DiffRow | null; side: "left" | "right" }) {
  const border = side === "left" ? "border-r border-line" : "";
  if (!row) {
    return <div className={`min-h-5 ${border}`} />;
  }
  if (row.kind === "meta") {
    return (
      <div className={`${border} bg-canvas px-3 py-0.5`}>
        <span className="font-mono text-[11px] leading-5 text-faint italic">{row.text}</span>
      </div>
    );
  }
  const tint =
    row.kind === "del"
      ? "bg-del-bg hover:bg-del-bg-hover"
      : row.kind === "add"
        ? "bg-add-bg hover:bg-add-bg-hover"
        : "";
  const numberColor = row.kind === "context" ? "text-faint" : "text-muted";
  return (
    <div className={`flex ${tint} ${border}`}>
      <span className={`${GUTTER} ${numberColor}`}>{side === "left" ? row.oldNo : row.newNo}</span>
      <code className="whitespace-pre px-3 font-mono text-[12px] leading-5 text-ink [tab-size:4]">
        {row.text}
      </code>
      <span className="min-w-3 flex-1" />
    </div>
  );
}

function HunkHeader({ header, first }: { header: string; first: boolean }) {
  const match = /^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@(.*)$/.exec(header);
  return (
    <div
      className={`w-full bg-panel-2 px-3 py-1 font-mono text-[11px] leading-5 ${
        first ? "" : "border-t border-line"
      }`}
    >
      {match ? (
        <>
          <span className="text-faint">@@ </span>
          <span className="text-cyan">-{match[1]} </span>
          <span className="text-cyan">+{match[2]} </span>
          <span className="text-faint">@@</span>
          {match[3] && <span className="text-muted">{match[3]}</span>}
        </>
      ) : (
        <span className="text-faint">{header}</span>
      )}
    </div>
  );
}

function FileCard({
  file,
  view,
  findingCount,
  collapsed,
  onToggle,
}: {
  file: DiffFile;
  view: "unified" | "split";
  findingCount: number;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <section
      className="overflow-hidden rounded-lg border border-line bg-canvas"
      aria-label={`Changes in ${file.path}`}
    >
      <header className="flex min-h-10 items-center gap-2 border-b border-line bg-panel-2 px-3 py-1.5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? `Expand ${file.path}` : `Collapse ${file.path}`}
          title={collapsed ? "Expand file" : "Collapse file"}
          className="grid size-6 shrink-0 place-items-center rounded text-faint transition hover:bg-panel-3 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
        >
          <ChevronDown
            size={14}
            className={collapsed ? "-rotate-90 transition-transform" : "transition-transform"}
          />
        </button>
        <p className="min-w-0 truncate font-mono text-[12px]">
          <span className="text-muted">{file.dir}</span>
          <span className="font-medium text-ink">{file.base}</span>
        </p>
        {findingCount > 0 && (
          <span className="shrink-0 rounded-full bg-lime-soft px-2 py-0.5 font-mono text-[10px] tabular-nums text-lime">
            {findingCount} finding{findingCount === 1 ? "" : "s"}
          </span>
        )}
        {!file.binary && (
          <span className="ml-auto flex shrink-0 items-center gap-2 font-mono text-[11px] tabular-nums">
            <span className="text-add">+{file.additions}</span>
            <span className="text-del">−{file.deletions}</span>
          </span>
        )}
      </header>
      {!collapsed &&
        (file.binary ? (
          <p className="px-3 py-3 font-mono text-[11px] text-faint">Binary file not shown</p>
        ) : file.hunks.length === 0 ? (
          <p className="px-3 py-3 font-mono text-[11px] text-faint">
            No textual changes in this file.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <div className="w-max min-w-full">
              {file.hunks.map((hunk, hunkIndex) => (
                <div key={`${file.key}-${hunkIndex}`}>
                  <HunkHeader header={hunk.header} first={hunkIndex === 0} />
                  {view === "unified"
                    ? hunk.rows.map((row, rowIndex) => (
                        <UnifiedRow key={`${hunkIndex}-${rowIndex}`} row={row} />
                      ))
                    : toSplitRows(hunk.rows).map((entry, rowIndex) =>
                        entry.kind === "meta" ? (
                          <div key={`${hunkIndex}-${rowIndex}`} className="grid grid-cols-2">
                            <SplitSide row={entry.row} side="left" />
                            <SplitSide row={null} side="right" />
                          </div>
                        ) : (
                          <div
                            key={`${hunkIndex}-${rowIndex}`}
                            className="grid w-max min-w-full grid-cols-2 hover:bg-panel-2"
                          >
                            <SplitSide row={entry.left} side="left" />
                            <SplitSide row={entry.right} side="right" />
                          </div>
                        ),
                      )}
                </div>
              ))}
            </div>
          </div>
        ))}
    </section>
  );
}

export function DiffView({
  diff,
  markFiles,
  className = "",
}: {
  diff: string;
  markFiles?: Record<string, number>;
  className?: string;
}) {
  const files = useMemo(() => parseDiff(diff), [diff]);
  const totals = useMemo(() => diffTotals(files), [files]);
  const [view, setView] = useState<"unified" | "split">("unified");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState(false);

  if (files.length === 0) {
    return (
      <p
        className={`rounded-lg border border-dashed border-line-strong px-6 py-8 text-center font-mono text-[12px] text-faint ${className}`}
      >
        No diff to display.
      </p>
    );
  }

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(diff);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={`grid gap-3 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-3 font-mono text-[11px] text-muted">
          <span>
            {files.length} file{files.length === 1 ? "" : "s"} changed
          </span>
          <span className="tabular-nums text-add">+{totals.additions}</span>
          <span className="tabular-nums text-del">−{totals.deletions}</span>
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void onCopy()}
            className="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1.5 font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint transition hover:border-line-strong hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
            {copied ? "Copied" : "Copy diff"}
          </button>
          <div
            className="flex items-center rounded-md border border-line bg-panel p-0.5"
            role="group"
            aria-label="Diff view"
          >
            {(["unified", "split"] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={view === option}
                onClick={() => setView(option)}
                className={`rounded px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-[0.06em] transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime ${
                  view === option ? "bg-panel-3 text-ink" : "text-faint hover:text-muted"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-3">
        {files.map((file) => (
          <FileCard
            key={file.key}
            file={file}
            view={view}
            findingCount={markFiles?.[file.path] ?? 0}
            collapsed={collapsed[file.key] ?? false}
            onToggle={() =>
              setCollapsed((current) => ({
                ...current,
                [file.key]: !(current[file.key] ?? false),
              }))
            }
          />
        ))}
      </div>
    </div>
  );
}
