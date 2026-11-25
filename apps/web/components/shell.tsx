import Link from "next/link";
import { Heart, Bookmark } from "lucide-react";
export function Header() {
  return (
    <>
      <div className="announcement">Made for the moments you want to keep.</div>
      <header className="site-header">
        <div className="header-inner">
          <Link className="wordmark" href="/" aria-label="keepsake3D home">
            <Heart size={26} strokeWidth={1.4} />
            <span>
              keepsake<span className="wordmark-3d">3D</span>
            </span>
          </Link>
          <nav aria-label="Main navigation">
            <Link href="/">The collection</Link>
            <Link href="/#how-it-works">How it works</Link>
            <Link href="/#our-story">Our story</Link>
          </nav>
          <Link
            className="saved-link"
            href="/studio"
            aria-label="Open your keepsake studio"
          >
            <Bookmark size={20} />
            <span className="desktop-label">Your keepsake</span>
            <span className="mobile-label">Create yours</span>
          </Link>
        </div>
      </header>
    </>
  );
}
export function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <Link className="wordmark" href="/">
          <Heart size={25} strokeWidth={1.4} />
          keepsake<span className="wordmark-3d">3D</span>
        </Link>
        <p>For the little things. And the big feelings.</p>
        <div>
          <Link href="/design-system">Design system</Link>
          <Link href="/admin">Operations</Link>
          <Link href="/#good-to-know">Good to know</Link>
        </div>
      </div>
      <div className="footer-bottom">
        <span>Keepsake 3D · Demo studio</span>
        <span>Thoughtfully imagined. Still being made.</span>
      </div>
    </footer>
  );
}
