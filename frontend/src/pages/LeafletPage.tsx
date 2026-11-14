import { useState } from "react";
import { Link } from "react-router";

import { API_BASE_URL } from "@/api/client";
import { authHeader } from "@/lib/auth";
import { useDrugs } from "@/api/queries";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate, useDocumentTitle } from "@/lib/format";

type Result = {
  event_id: string;
  event_date: string;
  claim_text: string;
  status: "propagated" | "partial" | "not_propagated" | "insufficient_evidence";
  quotes: string[];
  rationale: string;
};
type Check = {
  id: string;
  brand_name: string;
  results: Result[];
  consistency: {
    compared: number;
    max_similarity: number | null;
    duplicate_of: string | null;
    flagged: boolean;
  };
};

async function call<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  for (const [key, value] of Object.entries(authHeader())) {
    headers.set(key, value);
  }
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  const body = (await res.json()) as T & { detail?: string };
  if (!res.ok) throw new Error(body.detail ?? res.statusText);
  return body;
}

export function LeafletPage() {
  useDocumentTitle("Leaflet check");
  const drugs = useDrugs("");
  const [medicine, setMedicine] = useState("");
  const [drugId, setDrugId] = useState("");
  const [brand, setBrand] = useState("");
  const [maker, setMaker] = useState("");
  const [regNo, setRegNo] = useState("");
  const [text, setText] = useState("");
  const [source, setSource] = useState<"typed" | "pdf_text" | "vision">(
    "typed",
  );
  const [sha, setSha] = useState<string | null>(null);
  const [unclear, setUnclear] = useState<string[]>([]);
  const [check, setCheck] = useState<Check | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  async function run(label: string, task: () => Promise<void>) {
    setBusy(label);
    setMessage("");
    try {
      await task();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy("");
    }
  }

  const addMedicine = () =>
    run("add", async () => {
      const out = await call<{ ingredient: string; created: boolean }>(
        "/api/v1/medicines",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: medicine }),
        },
      );
      setMessage(
        out.created
          ? `${out.ingredient} added. Its US labels are fetched in the nightly run.`
          : `${out.ingredient} is already in the list.`,
      );
      await drugs.refetch();
    });

  const extract = (file: File) =>
    run("extract", async () => {
      const form = new FormData();
      form.append("file", file);
      const out = await call<{
        text: string;
        source: "pdf_text" | "vision";
        sha256: string;
        unclear_parts: string[];
      }>("/api/v1/leaflets/extract", { method: "POST", body: form });
      setText(out.text);
      setSource(out.source);
      setSha(out.sha256);
      setUnclear(out.unclear_parts);
    });

  const submit = () =>
    run("check", async () => {
      const out = await call<Check>("/api/v1/leaflets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          drug_id: drugId,
          brand_name: brand,
          manufacturer: maker || null,
          registration_no: regNo || null,
          source,
          file_sha256: sha,
          text,
        }),
      });
      setCheck(out);
    });

  const input = "w-full rounded-md border bg-background px-3 py-2 text-sm";
  const button =
    "rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50";

  return (
    <section aria-labelledby="leaflet-title" className="space-y-8">
      <header className="space-y-2">
        <h1 id="leaflet-title" className="text-3xl font-semibold">
          Leaflet check (Bangladesh)
        </h1>
        <p className="max-w-prose text-muted-foreground">
          Upload a medicine leaflet. Its text is compared with safety changes
          made to the US brand label. Uploads are unverified user submissions.
          Not medical advice.
        </p>
      </header>

      <div className="space-y-2 rounded-lg border p-4">
        <h2 className="font-medium">Add a medicine</h2>
        <div className="flex gap-2">
          <input
            aria-label="Generic name"
            className={input}
            placeholder="Generic name, e.g. atorvastatin"
            value={medicine}
            onChange={(e) => { setMedicine(e.target.value); }}
          />
          <button
            className={button}
            disabled={medicine.length < 2 || !!busy}
            onClick={() => void addMedicine()}
          >
            Add
          </button>
        </div>
      </div>

      <div className="space-y-3 rounded-lg border p-4">
        <h2 className="font-medium">Check a leaflet</h2>
        <select
          aria-label="Medicine"
          className={input}
          value={drugId}
          onChange={(e) => { setDrugId(e.target.value); }}
        >
          <option value="">Choose a medicine</option>
          {drugs.data?.items.map((d) => (
            <option key={d.id} value={d.id}>
              {d.ingredient}{" "}
              {d.events ? `(${d.events} US changes)` : "(data pending)"}
            </option>
          ))}
        </select>
        <div className="grid gap-2 sm:grid-cols-3">
          <input
            aria-label="Brand name"
            className={input}
            placeholder="Brand name"
            value={brand}
            onChange={(e) => { setBrand(e.target.value); }}
          />
          <input
            aria-label="Manufacturer"
            className={input}
            placeholder="Manufacturer"
            value={maker}
            onChange={(e) => { setMaker(e.target.value); }}
          />
          <input
            aria-label="DGDA registration no."
            className={input}
            placeholder="DGDA registration no. (optional)"
            value={regNo}
            onChange={(e) => { setRegNo(e.target.value); }}
          />
        </div>
        <label className="block text-sm">
          Leaflet photo or PDF (max 8 MB)
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf"
            className="mt-1 block text-sm"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void extract(file);
            }}
          />
        </label>
        {unclear.length > 0 && (
          <p role="alert" className="text-sm text-amber-700">
            Some parts could not be read: {unclear.join("; ")}. Please correct
            the text below.
          </p>
        )}
        <textarea
          aria-label="Leaflet text"
          className={`${input} min-h-48 font-mono`}
          placeholder="Extracted text appears here. Check it against the leaflet and fix any mistakes, or paste the text."
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (source === "pdf_text") setSource("typed");
          }}
        />
        <button
          className={button}
          disabled={!drugId || !brand || text.length < 40 || !!busy}
          onClick={() => void submit()}
        >
          {busy === "check"
            ? "Checking…"
            : busy === "extract"
              ? "Reading leaflet…"
              : "Compare with US changes"}
        </button>
        {message && <p className="text-sm">{message}</p>}
      </div>

      {check && (
        <div className="space-y-3">
          <h2 className="text-xl font-semibold">
            Results for {check.brand_name}
          </h2>
          {(check.consistency.flagged || check.consistency.duplicate_of) && (
            <p
              role="alert"
              className="rounded-md border border-amber-400 p-3 text-sm"
            >
              {check.consistency.duplicate_of
                ? "This exact file was uploaded before. "
                : `This leaflet's text differs strongly from ${check.consistency.compared} other upload(s) of the same brand. `}
              It may be a different edition or not genuine; verify the pack.
            </p>
          )}
          <ul className="space-y-3">
            {check.results.map((r) => (
              <li key={r.event_id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={r.status} />
                  <span className="text-xs text-muted-foreground">
                    US change {formatDate(r.event_date)}
                  </span>
                </div>
                <Link
                  to={`/events/${r.event_id}`}
                  className="mt-1 block hover:underline"
                >
                  {r.claim_text}
                </Link>
                {r.quotes.map((q) => (
                  <blockquote
                    key={q}
                    className="mt-1 border-l-2 pl-2 text-sm italic"
                  >
                    {q}
                  </blockquote>
                ))}
                <p className="mt-1 text-xs text-muted-foreground">
                  {r.rationale}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
