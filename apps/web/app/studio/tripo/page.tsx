import type { Metadata } from "next";
import TripoStudio from "@/components/tripo-studio";

export const metadata: Metadata = { title: "Tripo photo to 3D — Keepsake 3D" };
export default function TripoPage() {
  return <TripoStudio />;
}
