import Image from "next/image";
import Link from "next/link";
import Atmosphere from "@/components/Atmosphere";
import HeroSearch from "@/components/landing/HeroSearch";
import Saturn from "@/components/landing/Saturn";
import Voices from "@/components/landing/Voices";
import { AiIcon, AskIcon, CompareIcon, MaterialsIcon, ProblemIcon, SearchIcon, SolutionIcon, SourceIcon } from "@/components/landing/icons";
import styles from "./Landing.module.css";

const tools = [
  { name: "Evidence Explorer", label: "SEARCH", text: "Browse every NASA experiment record, with conditions, flags and source links.", href: "/explorer", action: "Explore evidence", Icon: SearchIcon },
  { name: "Materials", label: "ANSWER", text: "All 31 materials at your conditions: tested, estimated, or no direct evidence.", href: "/materials", action: "See all materials", Icon: MaterialsIcon },
  { name: "Scenario Ranker", label: "COMPARE", text: "Enter a scenario and find the closest tested conditions.", href: "/ranker", action: "Compare conditions", Icon: CompareIcon },
  { name: "Ask with Citations", label: "UNDERSTAND", text: "Ask a question; answers come only from the records, with sources.", href: "/ask", action: "Ask a question", Icon: AskIcon },
];

const compare: [string, string, string][] = [
  ["Where the answer comes from", "One Earth test report", "970 NASA records, microgravity and 1g side by side"],
  ["When nobody tested your case", "Silence, or a guess", "A labelled model estimate with its measured error, or an honest “no direct evidence”"],
  ["Checking a number", "Dig through scattered PDFs", "Every record links to its DOI or NASA page"],
  ["Earth vs space", "Assumed to match", "Shown together, never mixed, with the gap made visible"],
];

export default function Home() {
  return (
    <div className="shell" id="top">
      <Atmosphere />
      <header className="topbar">
        <Link href="/" className="brand" aria-label="Flame Atlas home">
          <span className="brand-mark"><Image src="/flame-atlas-logo.png" alt="" width={58} height={55} priority /></span>
          <span><strong>FLAME ATLAS</strong><small>COMBUSTION RESEARCH INTELLIGENCE</small></span>
        </Link>
        <nav aria-label="Main navigation">
          <Link href="/explorer">Evidence Explorer</Link>
          <Link href="/materials">Materials</Link>
          <Link href="/ranker">Scenario Ranker</Link>
          <Link href="/ask">Ask with Citations</Link>
        </nav>
        <span aria-hidden="true" />
      </header>

      <main className={styles.page}>
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroCopy}>
            <h1 id="hero-title">Explore fire<br /><span>beyond Earth.</span></h1>
            <p className={styles.lead}>Look up a material and the cabin conditions. Get NASA&apos;s tested evidence if it exists, a clearly labelled estimate if it does not, and the source behind every number.</p>
            <HeroSearch />
            <div className={styles.footnote}><span className={styles.dot} />Evidence-led. Every answer says whether it was tested.</div>
          </div>
          <Saturn />
        </section>

        <section id="tools" className={styles.tools} aria-label="Tools">
          <div className={styles.toolsGrid}>
            {tools.map(({ name, label, text, href, action, Icon }) => (
              <Link href={href} className={styles.toolCard} key={name}>
                <span className={styles.toolBg} aria-hidden="true" />
                <span className={styles.iconTile} aria-hidden="true"><span className={styles.pulse} /><span className={`${styles.pulse} ${styles.pulseLate}`} /><Icon /></span>
                <span className={styles.toolLabel}>{label}</span>
                <h3>{name}</h3>
                <p>{text}</p>
                <span className={styles.toolAction}>{action} <span aria-hidden="true">→</span></span>
              </Link>
            ))}
          </div>
        </section>

        <section id="why" className={styles.why} aria-labelledby="why-title">
          <div className={styles.sectionHead}>
            <span className={styles.kicker}>THE PROBLEM AND THE ANSWER</span>
            <h2 id="why-title">Fire in space is not fire on Earth.<br /><span>The data to prove it is scattered.</span></h2>
          </div>
          <div className={styles.ps}>
            <article className={`${styles.psCard} ${styles.problem}`}>
              <span className={styles.psIcon}><ProblemIcon /></span><h3>The problem</h3>
              <p>Spacecraft fire safety leans on Earth tests. In microgravity, buoyancy-driven airflow disappears and flames behave differently. NASA&apos;s microgravity results sit in many tables and papers, and in our data <strong>0 of 31 materials</strong> have a finished burn test at lunar-habitat air.</p>
            </article>
            <article className={`${styles.psCard} ${styles.solution}`}>
              <span className={styles.psIcon}><SolutionIcon /></span><h3>The solution</h3>
              <p>Ask about a material and conditions. Flame Atlas answers one of three ways: <strong>tested evidence</strong> from NASA records, a <strong>model estimate</strong> clearly marked “not tested”, or an honest <strong>“no direct evidence”</strong>. It never blurs them.</p>
            </article>
          </div>

          <div className={styles.tableWrap} role="region" aria-label="Comparison" tabIndex={0}>
            <table className={styles.compare}>
              <caption>How Flame Atlas compares with relying on Earth tests alone</caption>
              <thead><tr><th scope="col" /><th scope="col">Earth tests alone</th><th scope="col">Flame Atlas</th></tr></thead>
              <tbody>{compare.map(([k, a, b]) => <tr key={k}><th scope="row">{k}</th><td>{a}</td><td>{b}</td></tr>)}</tbody>
            </table>
          </div>

          <div className={styles.features}>
            <article className={styles.feature}><span className={styles.psIcon}><SourceIcon /></span><h3>Back to the original source</h3>
              <p>Every record carries its DOI or NASA link, the table or row it came from, and any data-quality flag. Click through and check it yourself.</p></article>
            <article className={styles.feature}><span className={styles.psIcon}><AiIcon /></span><h3>Help when nobody tested your case</h3>
              <p>If no study matches exactly what you asked, a model trained on 136 real microgravity runs suggests the closest case with a 95% interval. When it cannot narrow it down, it says “too uncertain to call”.</p></article>
          </div>
        </section>

        <Voices />
      </main>

      <footer className={styles.footer}>
        <Link href="/" className={styles.footBrand} aria-label="Flame Atlas home"><Image src="/flame-atlas-logo.png" alt="" width={34} height={32} /><strong>FLAME ATLAS</strong></Link>
        <span>NASA Space Apps Challenge · 2026. Preview mode shows interface examples, not verified measurements.</span>
        <Link href="#top">Back to top ↑</Link>
      </footer>
    </div>
  );
}
