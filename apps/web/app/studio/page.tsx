import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Your keepsake studio — Keepsake 3D",
};
import Studio from "@/components/studio";
export default function StudioPage() {
  return <Studio />;
}
