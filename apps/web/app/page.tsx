import Link from "next/link";
import {
  Camera,
  Box,
  Heart,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Plus,
  ChevronRight,
} from "lucide-react";
import ProductGallery from "@/components/product-gallery";
import { StatusBadge } from "@design/primitives";
const faqs = [
  [
    "Will my keepsake look exactly like my photos?",
    "The studio uses visible face proportions and suggested colors from your photos to shape a stylized figurine. You review who sits where, hair, glasses and colors before the build. The body and pose stay fixed. This beta does not guarantee an exact likeness or reproduce the concept artwork.",
  ],
  [
    "What kind of photos should I choose?",
    "Choose 1–3 well-lit JPEG, PNG, or WebP photos with clear, upright, front-facing faces. Each file may be up to 10 MB. Include both people, together or in separate photos; you explicitly choose which face belongs on each side.",
  ],
  [
    "How are my photos used?",
    "Uploads are stored privately on the server and are accessible only to your session. Face measurements and color suggestions are computed in your browser; no photos go to an external AI provider. Images expire within 24 hours, and you can delete your session and its files from the studio. On this temporary demo, a server restart may clear your session sooner.",
  ],
  [
    "Can I order one yet?",
    "Checkout is not active. The commercial master model, materials, dimensions, price, delivery terms, and physical print validation are still to be established. Approving a demo preview does not place an order.",
  ],
];
export default function Home() {
  return (
    <main id="main">
      <div className="page-width">
        <div className="breadcrumb">
          <Link href="/">The collection</Link>
          <ChevronRight size={13} />
          <span>Better Together</span>
        </div>
        <section className="product-layout">
          <ProductGallery />
          <div className="product-copy">
            <div className="inline product-kicker">
              <span className="eyebrow">THE BETTER TOGETHER COLLECTION</span>
              <StatusBadge>Photo studio · Beta</StatusBadge>
            </div>
            <h1>
              Two pieces.
              <br />
              <em>One story.</em>
            </h1>
            <p className="product-lede">
              Your favorite person. Your everyday magic.
              <br />A little keepsake of the two of you.
            </p>
            <div className="product-description">
              <h2>Better Together</h2>
              <p>
                A photo-inspired couple figurine, imagined on two halves of a
                heart. Because some things just belong together.
              </p>
            </div>
            <div className="personal-touches">
              <span>
                <Camera size={19} />
                Starts with your photos
              </span>
              <span>
                <Heart size={19} />
                Made personal with your names
              </span>
              <span>
                <Box size={19} />A 3D preview to make it yours
              </span>
            </div>
            <Link className="button button--primary main-cta" href="/studio">
              <Sparkles size={18} />
              Create your keepsake
            </Link>
            <p className="cta-caption">Explore the demo · No payment needed</p>
            <div className="privacy-line">
              <ShieldCheck size={19} />
              <span>Your photos stay private. Your story stays yours.</span>
            </div>
            <details className="product-note">
              <summary>
                About this early collection <Plus size={17} />
              </summary>
              <p>
                The image is concept art. The studio generates a simpler,
                clearly labeled 3D demo. Commercial materials, pricing, and
                availability are still being developed.
              </p>
            </details>
          </div>
        </section>
        <div className="values-strip">
          <span>
            <Heart />
            Little details, big feelings
          </span>
          <span>
            <SlidersHorizontal />
            Thoughtfully personalized
          </span>
          <span>
            <ShieldCheck />
            Review before you approve
          </span>
        </div>
        <section className="how-section" id="how-it-works">
          <div className="section-heading">
            <p className="eyebrow">FROM A MOMENT TO A MEMORY</p>
            <h2>
              A little you. A little us.
              <br />
              <em>A keepsake to hold onto.</em>
            </h2>
          </div>
          <div className="steps-grid">
            <article>
              <span className="line-icon">
                <Camera />
              </span>
              <h3>Start with a favorite photo</h3>
              <p>
                A shared laugh, a quiet moment. Choose photos that feel like the
                two of you.
              </p>
            </article>
            <article>
              <span className="line-icon">
                <Box />
              </span>
              <h3>See your story take shape</h3>
              <p>
                Explore a 3D preview. Look a little closer, turn it around, and
                review the details.
              </p>
            </article>
            <article>
              <span className="line-icon">
                <Heart />
              </span>
              <h3>Make it yours, together</h3>
              <p>
                Add your names and approve your preview when it feels right.
                Every little detail matters.
              </p>
            </article>
          </div>
        </section>
        <section className="story-section" id="our-story">
          <div className="story-mark">
            <Heart size={80} strokeWidth={0.8} />
            <span>
              better
              <br />
              <em>together.</em>
            </span>
          </div>
          <div>
            <p className="eyebrow">A PLACE FOR YOUR EVERYDAY MAGIC</p>
            <h2>
              Not every big feeling
              <br />
              needs a grand gesture.
            </h2>
            <p>
              Sometimes, it’s the person beside you. The familiar smile. The
              ordinary day you’d live all over again.
            </p>
            <p>
              We’re exploring a way to give those small, wonderful things a
              shape — a keepsake with a story only you can tell.
            </p>
            <Link className="text-link" href="/studio">
              Explore your keepsake
            </Link>
          </div>
        </section>
        <section className="faq-section" id="good-to-know">
          <div>
            <p className="eyebrow">A FEW THOUGHTFUL DETAILS</p>
            <h2>Good to know.</h2>
            <p>A little clarity before you begin.</p>
          </div>
          <div className="faq-list">
            {faqs.map(([q, a]) => (
              <details key={q}>
                <summary>
                  {q}
                  <Plus size={19} />
                </summary>
                <p>{a}</p>
              </details>
            ))}
          </div>
        </section>
      </div>
      <section className="closing-note">
        <Heart size={25} />
        <p>Some stories are better together.</p>
        <Link href="/studio" className="button button--secondary">
          Start your story
        </Link>
      </section>
    </main>
  );
}
