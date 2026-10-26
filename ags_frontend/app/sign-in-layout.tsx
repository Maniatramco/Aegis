import type { ReactNode } from "react";
import Image from "next/image";

/* Connector curves traced from aegis-banner.jpg (906x1280 pixel space): models flow in from the left, knowledge sources from the right. */
const KNOWLEDGE_LINKS = [
  { path: "M200 541 C235 545 255 580 290 616", tone: "cyan", delay: 0 },
  { path: "M200 608 C235 609 255 630 290 644", tone: "violet", delay: 0.4 },
  { path: "M200 675 L290 675", tone: "cyan", delay: 0.8 },
  { path: "M200 741 C235 740 255 712 290 699", tone: "violet", delay: 0.2 },
  { path: "M200 811 C235 808 255 768 290 737", tone: "violet", delay: 0.6 },
  { path: "M690 542 C655 546 635 581 600 617", tone: "cyan", delay: 0.3 },
  { path: "M690 609 C655 610 635 631 600 645", tone: "cyan", delay: 0.7 },
  { path: "M690 675 L600 675", tone: "cyan", delay: 1.1 },
  { path: "M690 741 C655 740 635 712 600 699", tone: "cyan", delay: 0.5 },
  { path: "M690 805 C655 802 635 766 600 739", tone: "cyan", delay: 0.9 },
] as const;
const FLOW_SECONDS = 2.6;
const PILLARS = ["Secure by design", "Governed and compliant", "Accurate and traceable", "Flexible and scalable", "Observe and improve"];

/** Decorative dots that travel along the banner's own connector lines into the shield. */
function KnowledgeFlow() {
  return <svg className="login-flow" viewBox="0 0 906 1280" aria-hidden="true" focusable="false">
    {KNOWLEDGE_LINKS.flatMap((link, index) => [link.delay, link.delay + FLOW_SECONDS / 2].map(start => {
      const begin = `${start}s`, dur = `${FLOW_SECONDS}s`;
      return <g key={`${index}-${start}`} className={`login-flow-dot ${link.tone}`} opacity={0}>
        <circle r={8} className="halo" /><circle r={3} className="core" />
        <animateMotion dur={dur} begin={begin} repeatCount="indefinite" path={link.path} />
        <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.15;0.8;1" dur={dur} begin={begin} repeatCount="indefinite" />
      </g>;
    }))}
  </svg>;
}

/** Keep the sign-in task first in reading order at every viewport size. */
export function SignInLayout({ children }: { children: ReactNode }) {
  return <main className="login-shell">
    <div className="login-ambient" aria-hidden="true"><span className="login-glow cyan" /><span className="login-glow violet" /></div>
    <div className="login-layout">
      <section className="login-card" aria-labelledby="login-heading">
        <div className="login-identity">
          <Image src="/aegis-platform-logo.png" alt="" width={48} height={48} />
          <div><p className="login-brand-name">Aegis</p>
            <p className="login-brand-tagline">Secure Data Lakehouse and AI Platform</p></div>
        </div>
        {children}
        <div className="login-pillars">
          <span className="login-pillars-label">Built for</span>
          <div className="login-pillars-window"><ul className="login-pillars-track">
            {PILLARS.map(pillar => <li key={pillar}>{pillar}</li>)}
          </ul></div>
        </div>
      </section>
      <section className="login-story" aria-label="Aegis platform artwork">
        <figure className="login-illustration">
          <Image className="login-artwork" src="/aegis-banner.jpg" alt="Aegis shield and network artwork"
            width={906} height={1280} sizes="(max-width: 760px) calc(100vw - 36px), (max-height: 820px) 465px, 540px" priority />
          <KnowledgeFlow />
        </figure>
      </section>
    </div>
  </main>;
}
