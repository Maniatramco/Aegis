# Aegis browser sharing through VS Code - 2026-10-10

Current temporary testing URL: **https://hd260kx9-3003.inc1.devtunnels.ms**

## Steps completed

1. Confirmed the Docker application is healthy at http://localhost:3003 and opened the active `Aegis` checkout in desktop VS Code.
2. Opened the built-in Ports view and forwarded local port **3003**. Completed VS Code's GitHub sign-in using the existing signed-in account and returned authorization to VS Code. No GitHub password was entered by automation.
3. Created the HTTPS Microsoft Dev Tunnels address above. Switched the forwarded port from Private to **Public**, confirming VS Code's public-forwarding notice, so a colleague with a different GitHub account can reach the Aegis login screen.
4. Updated only `AEGIS_PUBLIC_ORIGIN` in the active project's private `.env.oracle` to the HTTPS origin (without a trailing slash). Recreated the API container using the existing Oracle/GPU/Oracle-client Compose configuration. Existing data volumes and model containers were preserved. The web container remained running. Localhost origins remain allowed.
5. Ran actual Chromium checks through the external HTTPS address: secure browser context and UUID API present; anonymous `/api/auth/me` returns 401; QA sign-in/session works; saved merged extraction opens and its Review heading is visible/focused; logout revokes the session. All **5 checks passed**, with no browser JavaScript errors.

This is public application forwarding for temporary testing. Anyone who obtains the URL can reach the login screen; Aegis authentication is still required for account-owned datasets, documents and results. Only web port 3003 was forwarded through VS Code. The existing Oracle listener remains bound to laptop loopback; no Oracle, Qdrant, Ollama or API ports were added to the tunnel. Following the additional account-creation request, **User1** and **User2** were provisioned with separate cryptographically generated passwords. Passwords were verified through the forwarded HTTPS login and displayed only through the private local credential viewer. A Windows-account-encrypted credential receipt is kept under the ignored secrets directory, separate from this report.

## What to give your colleague

Send the HTTPS application address and their own Aegis login through your usual private channel. No Docker, VS Code, local model installation or repository clone is required on their computer. Their account has its own workspace; your saved datasets are not automatically shared with a separate account.

If a new login is needed, from the active Aegis folder run:

```powershell
.\scripts\create-colleague.ps1 -Username colleague-name
```

Enter a unique password privately when prompted. Do not send the project environment or database secrets.

## Keep available and stop sharing

Keep the laptop awake, Docker Desktop running, and the VS Code window hosting the Ports entry open. Losing network access or closing the forwarding session interrupts the external link even if Docker continues running locally.

To stop external sharing: in VS Code **Ports**, right-click **3003** and choose **Stop Forwarding Port**. Docker and http://localhost:3003 continue running. You can restore `AEGIS_PUBLIC_ORIGIN=http://localhost:3003` afterwards and recreate the API using the same existing Compose files.

If a later forwarding session produces a different URL, update `AEGIS_PUBLIC_ORIGIN` and recreate the API before testing the new link. This setup is temporary developer sharing, not an OCI/OKE deployment or production-hosting validation.

## Evidence

`results/vscode-sharing-2026-10-10/forwarded-access.json` contains the actual 5-check report. The other files show the public port entry and review reached through HTTPS. No application responses were mocked. No customer results were edited. `ags_frontend/ags_tests/forwarded-access-live.js` is the repeatable browser runner; its private QA credentials arrive on stdin and are not saved in the report.

## Colleague accounts

- **User1** and **User2** were created using the operator provisioning command; Oracle stores password hashes.
- Both passed actual HTTPS login/session, empty-new-workspace, account-ownership protection (another account's QA extraction returns 403/404), and logout/session-revocation checks.
- Accounts have separate empty workspaces. No existing user's credentials or documents were modified.
- The operator can reopen the private masked credential viewer by running `secrets/colleague-logins/Open-Logins.ps1` in the active Aegis checkout, on the same Windows account. Passwords are not part of this report, test evidence, git or chat.
- See `results/vscode-sharing-2026-10-10/colleague-accounts.json` for the sanitized verification evidence.
