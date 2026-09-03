"use client";

/**
 * The library: what you have uploaded, and the way to upload more.
 *
 * Each document row can turn itself into flashcards, open a chat scoped to
 * itself, show its chunks, or go. The dropzone accepts .txt, .md and .pdf,
 * the three types the API extracts text from.
 */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { BorderBeam } from "@/components/magicui/border-beam";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { UploadIcon } from "@/components/app/icons";
import { Button } from "@/components/ui/button";
import { ExpandCapsule } from "@/components/ui/product";
import { api, ApiError, type CardStats, type Chunk, type Document } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const ACCEPT = ".txt,.md,.markdown,.pdf";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export default function LibraryPage() {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [stats, setStats] = useState<CardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      Promise.all([api.documents.list(), api.cards.stats()])
        .then(([docs, cardStats]) => {
          setDocuments(docs);
          setStats(cardStats);
          setError(null);
        })
        .catch((e: unknown) => setError(message(e))),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const chunks = documents?.reduce((n, d) => n + d.chunk_count, 0) ?? 0;

  return (
    <div className="flex flex-col gap-xxl">
      <BlurFade inView={false}>
        <header className="flex flex-wrap items-end justify-between gap-lg">
          <div>
            <p className="text-body-strong text-ink-muted-48">Library</p>
            <h1 className="mt-xs text-display-lg text-ink">Your material.</h1>
          </div>
          <dl className="flex gap-xl">
            <Stat label="documents" value={documents?.length ?? 0} />
            <Stat label="passages" value={chunks} />
            <Stat label="cards" value={stats?.total ?? 0} />
          </dl>
        </header>
      </BlurFade>

      <BlurFade inView={false} delay={0.08}>
        <UploadDropzone onUploaded={load} />
      </BlurFade>

      {error ? (
        <p role="alert" className="text-body text-ink">
          {error}
        </p>
      ) : null}

      {documents && documents.length === 0 ? (
        <BlurFade inView={false} delay={0.16}>
          <div className="rounded-lg bg-canvas-parchment p-xxl text-center">
            <p className="font-display text-tagline text-ink">Nothing here yet.</p>
            <p className="mx-auto mt-xs max-w-[40ch] text-body text-lead-grey">
              Drop a lecture, a chapter or your own notes above. Recall splits it into passages, embeds them, and everything
              else follows from that.
            </p>
          </div>
        </BlurFade>
      ) : null}

      <ul className="flex list-none flex-col gap-sm p-0">
        <AnimatePresence initial={false}>
          {documents?.map((doc, i) => (
            <motion.li
              key={doc.id}
              layout
              initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.98, filter: "blur(4px)" }}
              transition={{ duration: 0.35, delay: Math.min(i, 8) * 0.04 }}
            >
              <DocumentRow doc={doc} onChanged={load} />
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-right">
      <dt className="text-caption text-lead-grey">{label}</dt>
      <dd className="m-0 font-display text-display-md text-ink">
        <NumberTicker value={value} />
      </dd>
    </div>
  );
}

/* ---- upload ------------------------------------------------------------------ */

type Job = { name: string; status: "uploading" | "done" | "error"; detail?: string };

function UploadDropzone({ onUploaded }: { onUploaded: () => Promise<void> }) {
  const [dragging, setDragging] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = jobs.some((j) => j.status === "uploading");

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      if (list.length === 0) return;
      setJobs(list.map((f) => ({ name: f.name, status: "uploading" as const })));
      for (const file of list) {
        try {
          await api.documents.upload(file);
          setJobs((js) => js.map((j) => (j.name === file.name ? { ...j, status: "done" } : j)));
        } catch (e) {
          setJobs((js) => js.map((j) => (j.name === file.name ? { ...j, status: "error", detail: message(e) } : j)));
        }
      }
      await onUploaded();
      setTimeout(() => setJobs((js) => js.filter((j) => j.status === "error")), 1800);
    },
    [onUploaded],
  );

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    void upload(e.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "relative flex flex-col items-center gap-sm rounded-lg border border-dashed border-hairline px-lg py-xxl text-center transition-colors",
        dragging ? "border-primary bg-canvas-parchment" : "bg-surface-pearl",
      )}
    >
      {busy ? <BorderBeam size={90} duration={4} /> : null}
      <span className="inline-flex size-11 items-center justify-center rounded-pill bg-canvas text-primary">
        <UploadIcon className="size-6" />
      </span>
      <p className="font-display text-tagline text-ink">{busy ? "Reading and embedding…" : "Drop a file to add it."}</p>
      <p className="text-caption text-lead-grey">.txt, .md or .pdf · up to 10 MB · everything stays on this machine</p>
      <input ref={inputRef} type="file" accept={ACCEPT} multiple hidden onChange={(e) => e.target.files && void upload(e.target.files)} />
      <Button variant="secondary" className="mt-xs" disabled={busy} onClick={() => inputRef.current?.click()}>
        Choose files
      </Button>

      {jobs.length ? (
        <ul className="mt-sm flex list-none flex-col gap-xxs p-0 text-caption">
          {jobs.map((j) => (
            <li key={j.name} className={j.status === "error" ? "text-ink" : "text-lead-grey"}>
              {j.status === "uploading" ? "↑ " : j.status === "done" ? "✓ " : "✕ "}
              {j.name}
              {j.detail ? ` — ${j.detail}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* ---- one document ------------------------------------------------------------ */

function DocumentRow({ doc, onChanged }: { doc: Document; onChanged: () => Promise<void> }) {
  const [generating, setGenerating] = useState<"idle" | "working" | "error">("idle");
  const [generated, setGenerated] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [chunks, setChunks] = useState<Chunk[] | null>(null);

  const generate = async () => {
    setGenerating("working");
    setNote(null);
    try {
      const cards = await api.cards.generate(doc.id, 3);
      setGenerated(cards.length);
      setNote(cards.length ? `${cards.length} new cards, due now in Review.` : "Every passage already has cards.");
      setGenerating("idle");
      await onChanged();
    } catch (e) {
      setGenerating("error");
      setNote(message(e));
    }
  };

  const toggle = async () => {
    setExpanded((v) => !v);
    if (!chunks) setChunks((await api.documents.get(doc.id)).chunks);
  };

  const remove = async () => {
    if (!window.confirm(`Delete “${doc.title}”? Cards made from it stay.`)) return;
    await api.documents.delete(doc.id);
    await onChanged();
  };

  return (
    <article className="relative rounded-lg border border-hairline bg-canvas p-lg">
      {generating === "working" ? <BorderBeam size={80} duration={3} /> : null}
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div className="min-w-0">
          <h2 className="truncate text-tagline text-ink">{doc.title}</h2>
          <p className="mt-xxs text-caption text-lead-grey">
            {doc.filename} · {formatBytes(doc.size_bytes)} · {doc.chunk_count} passage{doc.chunk_count === 1 ? "" : "s"} ·{" "}
            {formatDate(doc.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-xs">
          <Button variant="primary" className="min-h-9 px-md py-xs text-caption" disabled={generating === "working"} onClick={generate}>
            {generating === "working" ? "Writing cards…" : generated !== null ? "Generate more" : "Generate cards"}
          </Button>
          <Link href={`/chat?doc=${doc.id}`} data-pressable className="inline-flex min-h-9 items-center rounded-pill bg-canvas-parchment px-md py-xs text-caption text-ink">
            Ask about it
          </Link>
          <button type="button" onClick={remove} className="min-h-9 cursor-pointer border-0 bg-transparent px-xs text-caption text-ink-muted-48 hover:text-ink">
            Delete
          </button>
        </div>
      </div>

      {note ? (
        <p role="status" className={cn("mt-sm text-caption", generating === "error" ? "text-ink" : "text-primary")}>
          {note}
        </p>
      ) : null}

      <div className="mt-md">
        <ExpandCapsule label={expanded ? "Hide passages" : "Show passages"} expanded={expanded} onClick={toggle} />
      </div>
      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.ol
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="m-0 mt-md flex list-none flex-col gap-xs overflow-hidden p-0"
          >
            {(chunks ?? []).map((c) => (
              <li key={c.id} className="rounded-md bg-canvas-parchment p-md text-caption text-ink-muted-80">
                <span className="mr-xs text-ink-muted-48">§{c.position + 1}</span>
                {c.text.length > 260 ? `${c.text.slice(0, 260)}…` : c.text}
              </li>
            ))}
            {!chunks ? <li className="text-caption text-lead-grey">Loading…</li> : null}
          </motion.ol>
        ) : null}
      </AnimatePresence>
    </article>
  );
}
