"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, KeyRound, X } from "lucide-react";

export default function PasswordRecoveryPage() {
  const heading = useRef<HTMLHeadingElement>(null);
  const router = useRouter();
  useEffect(() => {
    heading.current?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") router.push("/");
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [router]);

  return (
    <main className="recovery-shell">
      <section className="recovery-card" aria-labelledby="recovery-heading">
        <header className="recovery-header">
          <span className="brand"><img src="/aegis-logo.png" alt="" width={32} height={32} /> Aegis</span>
          <Link href="/" className="btn icon" aria-label="Close password recovery"><X size={18} /></Link>
        </header>
        <div className="eyebrow">PASSWORD RECOVERY</div>
        <h1 id="recovery-heading" ref={heading} tabIndex={-1}>Recover your access</h1>
        <p className="muted">Your account, documents, and model settings stay in place.</p>
        <div className="notice">
          <KeyRound size={18} aria-hidden="true" />
          <p>First, check your password manager for a saved Aegis password. If someone else manages this workspace, ask them to help you recover access.</p>
        </div>
        <h2>Reset on the computer running Aegis</h2>
        <p>A local installation owner can use the recovery tool in a private terminal. This page guides you through the steps; it does not change your password.</p>
        <ol className="recovery-steps">
          <li><strong>Stop Aegis.</strong> Stop its API, worker, and frontend. Keep your existing data folder. Ollama can stay running.</li>
          <li><strong>Run the local recovery tool.</strong> It creates a private backup before changing the existing administrator password.</li>
          <li><strong>Enter your new password privately.</strong> Enter 12 to 200 characters twice at the hidden terminal prompts, then type <code>RESET</code> to confirm. Never send your password in chat.</li>
          <li><strong>Restart and sign in.</strong> Use your existing username and new password. Previous sign-in sessions will end.</li>
        </ol>
        <details className="recovery-instructions">
          <summary>Local operator instructions</summary>
          <p>For SQLite installations only. Activate the Aegis Python environment and open the repository folder in your terminal. Stop all API and worker instances, including any using custom ports.</p>
          <p>Replace the two placeholders with the existing database path and administrator username. Do not put your password in this command.</p>
          <pre><code>{'python scripts/reset_admin_password.py\n  --database "<existing-data-folder>/control.db"\n  --username "<your-username>"\n  --services-stopped'}</code></pre>
          <p>Run the command on one line. Keep the generated backup private. Do not create a new database or repeat first-run setup.</p>
          <a href="https://github.com/Maniatramco/Aegis/blob/feat/local-ollama/docs/PASSWORD_RECOVERY.md" target="_blank" rel="noreferrer">Read the full operator runbook (opens a new tab)</a>
        </details>
        <Link href="/" className="btn primary recovery-back"><ArrowLeft size={16} aria-hidden="true" /> Back to sign in</Link>
      </section>
    </main>
  );
}
