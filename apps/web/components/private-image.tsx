"use client";
import { useEffect, useState } from "react";
import { privateBlob, type Session } from "@/lib/api";
export function usePrivateBlob(
  url: string | undefined,
  session: Session | null,
  retry = 0,
) {
  const [state, setState] = useState<{ url: string; error: string }>({
    url: "",
    error: "",
  });
  useEffect(() => {
    setState({ url: "", error: "" });
    if (!url || !session) return;
    let active = true,
      local = "";
    privateBlob(url, session)
      .then((blob) => {
        if (active) {
          local = URL.createObjectURL(blob);
          setState({ url: local, error: "" });
        }
      })
      .catch((error) => {
        if (active) setState({ url: "", error: error.message });
      });
    return () => {
      active = false;
      if (local) URL.revokeObjectURL(local);
    };
  }, [url, session?.id, session?.token, retry]);
  return state;
}
export default function PrivateImage({
  url,
  session,
  alt,
}: {
  url: string;
  session: Session;
  alt: string;
}) {
  const blob = usePrivateBlob(url, session);
  return blob.url ? (
    <img src={blob.url} alt={alt} />
  ) : (
    <span className="image-loading" role="status">
      {blob.error || "Loading photo…"}
    </span>
  );
}
