
import Image from "next/image";
import Link from "next/link";
import Atmosphere from "@/components/Atmosphere";
import styles from "./LandingPage.module.css";

const tools = [
  {
    number: "01",
    name: "Evidence Explorer",
    label: "DISCOVER",
    description:
      "Search combustion experiments, filter conditions, and inspect the available evidence.",
    href: "/explorer",
    action: "Explore evidence",
    symbol: "⌕",
  },
  {
    number: "02",
    name: "Scenario Ranker",
    label: "COMPARE",
    description:
      "Enter a scenario and examine the closest available experimental conditions.",
    href: "/ranker",
    action: "Compare conditions",
    symbol: "◎",
  },
  {
    number: "03",
    name: "Ask with Citations",
    label: "UNDERSTAND",
    description:
      "Ask research questions and review cited answers when the live service is available.",
    href: "/ask",
    action: "Ask a question",
    symbol: "✳",
  },
];

function Brand() {
  return (
    <Link href="/" className={styles.brand} aria-label="Flame Atlas home">
      <Image
        src="/flame-atlas-logo.png"
        alt=""
        width={58}
        height={58}
        className={styles.logo}
        priority
      />
      <span className={styles.brandCopy}>
        <strong>FLAME ATLAS</strong>
        <small>COMBUSTION RESEARCH INTELLIGENCE</small>
      </span>
    </Link>
  );
}

function FlameOrb() {
  return (
    <div
      className={styles.orbScene}
      role="img"
      aria-label="Decorative conceptual spherical flame with orbital rings"
    >
      <div className={styles.orbHalo} />
      <div className={styles.orbGrid} />
      <div className={styles.orbitA} />
      <div className={styles.orbitB} />
      <div className={styles.orbitC} />

      <div className={styles.flameOrb}>
        <div className={styles.flameTexture} />
        <div className={styles.flameLight} />
      </div>

      <div className={styles.orbCrosshairA}>+</div>
      <div className={styles.orbCrosshairB}>+</div>
    </div>
  );
}

export default function Home() {
  return (
    <main className={styles.page} id="top">
      <Atmosphere />

      <header className="topbar">
        <Link href="/" className="brand" aria-label="Flame Atlas home">
          <span className="brand-mark">
            <Image
              src="/flame-atlas-logo.png"
              alt="Flame Atlas logo"
              width={58}
              height={55}
              priority
            />
          </span>

          <span>
            <strong>FLAME ATLAS</strong>
            <small>COMBUSTION RESEARCH INTELLIGENCE</small>
          </span>
        </Link>

        <nav aria-label="Main navigation">
          <Link href="/explorer">Evidence Explorer</Link>
          <Link href="/ranker">Scenario Ranker</Link>
          <Link href="/ask">Ask with Citations</Link>
        </nav>

        <div className="mode-switch">
          <Link href="/explorer" className={styles.workspaceModeLink}>
            Open Workspace
          </Link>
        </div>
      </header>

      <section className={styles.hero} aria-labelledby="hero-title">
        <div className={styles.heroCopy}>
          <span className={styles.kicker}>
            MICROGRAVITY COMBUSTION RESEARCH
          </span>

          <h1 id="hero-title">
            Explore fire
            <br />
            <span>beyond Earth.</span>
          </h1>

          <p className={styles.heroDescription}>
            Discover combustion experiments, compare research conditions,
            and explore the evidence behind fire safety in space.
          </p>

          <div className={styles.heroActions}>
            <Link href="/explorer" className={styles.primaryButton}>
              Explore Evidence <span aria-hidden="true">→</span>
            </Link>
            <Link href="#tools" className={styles.secondaryButton}>
              See How It Works <span aria-hidden="true">↓</span>
            </Link>
          </div>

          <div className={styles.heroFootnote}>
            <span className={styles.statusDot} />
            Evidence-led research exploration
          </div>
        </div>

        <FlameOrb />
      </section>

      <section id="tools" className={styles.toolsSection}>
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>THE RESEARCH WORKSPACE</span>
            <h2>
              One workspace.
              <br />
              <span>Three ways to explore.</span>
            </h2>
          </div>

          <p>
            Start with an experiment, explore related conditions,
            or ask a question. Choose the tool that fits your research.
          </p>
        </div>

        <div className={styles.toolsGrid}>
          {tools.map((tool) => (
            <article className={styles.toolCard} key={tool.number}>
              <div className={styles.cardTop}>
                <span>{tool.number} / {tool.label}</span>
                <span className={styles.cardArrow} aria-hidden="true">
                  ↗
                </span>
              </div>

              <div className={styles.cardVisual} aria-hidden="true">
                <span className={styles.visualRing} />
                <span className={styles.visualSymbol}>{tool.symbol}</span>
                <span className={styles.scanLine} />
              </div>

              <h3>{tool.name}</h3>
              <p>{tool.description}</p>

              <Link href={tool.href} className={styles.cardLink}>
                {tool.action} <span aria-hidden="true">→</span>
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.scienceSection}>
        <div className={styles.scienceVisual} aria-hidden="true">
          <span className={styles.scienceCircle} />
          <span className={styles.scienceOrbit} />
          <span className={styles.scienceCenter}>μg</span>
        </div>

        <div className={styles.scienceCopy}>
          <span className={styles.kicker}>WHY MICROGRAVITY MATTERS</span>
          <h2>
            Different gravity.
            <br />
            <span>Different flame behavior.</span>
          </h2>

          <p>
            In microgravity, buoyancy-driven airflow is greatly reduced.
            Studying how flames behave under these conditions helps
            researchers understand spacecraft fire safety.
          </p>

          <Link href="/explorer" className={styles.inlineLink}>
            Discover the experiments <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </section>

      <section className={styles.integritySection}>
        <div>
          <span className={styles.kicker}>SCIENTIFIC INTEGRITY</span>
          <h2>Follow the evidence.</h2>

          <p>
            Flame Atlas keeps source information and research limitations
            visible. Preview mode contains interface examples, not verified
            experimental measurements. Live features depend on the
            connected research service.
          </p>
        </div>

        <Link href="/explorer" className={styles.primaryButton}>
          Enter Flame Atlas <span aria-hidden="true">→</span>
        </Link>
      </section>

      <footer className={styles.footer}>
        <Brand />
        <span>Microgravity Combustion Research · 2026</span>
        <Link href="#top">Back to top ↑</Link>
      </footer>
    </main>
  );
}
