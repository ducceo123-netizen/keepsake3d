"use client";
import { useState } from "react";
import { LockKeyhole, RefreshCw } from "lucide-react";
import { BrandButton, ErrorState, StatusBadge } from "@design/primitives";
import { api } from "@/lib/api";
type Job = {
  id: string;
  session_id: string;
  revision: number;
  state: string;
  attempts: number;
  created_at: string;
  error_code?: string;
};
export default function Operations() {
  const [token, setToken] = useState(""),
    [jobs, setJobs] = useState<Job[] | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    setError("");
    try {
      const data = await api<{ jobs: Job[] }>("/api/v1/admin/jobs", null, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setJobs(data.jobs);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main" className="page-width operations">
      <div className="inline">
        <p className="eyebrow">STUDIO OPERATIONS</p>
        <StatusBadge>Read-only · Production disabled</StatusBadge>
      </div>
      <h1>Builds & revisions</h1>
      <p>
        Inspect demo jobs. Preview approval and manufacturing approval
        remain separate.
      </p>
      {jobs === null ? (
        <form
          className="operator-login"
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
        >
          <LockKeyhole />
          <h2>Operator access</h2>
          <p>Use the operator token configured by the studio administrator.</p>
          <label className="field">
            Operator token
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
            />
          </label>
          <BrandButton type="submit" loading={busy}>
            View builds
          </BrandButton>
        </form>
      ) : (
        <>
          <div className="jobs-toolbar">
            <span>{jobs.length} recent builds</span>
            <BrandButton variant="secondary" loading={busy} onClick={load}>
              <RefreshCw size={16} />
              Refresh
            </BrandButton>
            <BrandButton
              variant="text"
              onClick={() => {
                setJobs(null);
                setToken("");
              }}
            >
              Lock console
            </BrandButton>
          </div>
          {jobs.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Build</th>
                    <th>Revision</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.id}>
                      <td>
                        <code>{j.id.slice(0, 12)}</code>
                        {j.error_code && <p>{j.error_code}</p>}
                      </td>
                      <td>{j.revision}</td>
                      <td>
                        <StatusBadge
                          tone={
                            j.state === "FAILED"
                              ? "error"
                              : j.state === "PREVIEW_READY"
                                ? "success"
                                : "neutral"
                          }
                        >
                          {j.state.replaceAll("_", " ").toLowerCase()}
                        </StatusBadge>
                      </td>
                      <td>{j.attempts}</td>
                      <td>{new Date(j.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-jobs">
              No builds yet. Create a preview in the studio to see its job here.
            </div>
          )}
        </>
      )}
      {error && <ErrorState>{error}</ErrorState>}
    </main>
  );
}
