import type { ReactNode } from "react";
import Image from "next/image";

/** Keep the sign-in task first in reading order at every viewport size. */
export function SignInLayout({ children }: { children: ReactNode }) {
  return <main className="login-shell"><div className="login-layout">
    <section className="login-card" aria-labelledby="login-heading">
      <div className="login-identity">
        <Image src="/aegis-platform-logo.png" alt="" width={48} height={48} />
        <div><p className="login-brand-name">Aegis</p>
          <p className="login-brand-tagline">Secure Data Lakehouse and AI Platform</p></div>
      </div>
      {children}
    </section>
    <section className="login-story" aria-label="Aegis platform artwork">
      <figure className="login-illustration">
        <Image className="login-artwork" src="/aegis-banner.jpg" alt="Aegis shield and network artwork"
          width={906} height={1280} sizes="(max-width: 760px) calc(100vw - 36px), (max-height: 820px) 465px, 540px" priority />
      </figure>
    </section>
  </div></main>;
}
