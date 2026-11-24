"use client";
import { useState } from "react";
import { Expand, ImageIcon, Box } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
export default function ProductGallery() {
  const [full, setFull] = useState(false);
  return (
    <div className="product-gallery">
      <div className={`product-image ${full ? "product-image--full" : ""}`}>
        <img
          src="/better-together-concept.png"
          alt="Concept artwork of a stylized seated couple on two heart-shaped base halves"
          fetchPriority="high"
        />
        <span className="image-label">ART DIRECTION · CONCEPT IMAGE</span>
        <Dialog.Root>
          <Dialog.Trigger
            className="expand-button"
            aria-label="View full concept artwork"
          >
            <Expand size={19} />
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="dialog-overlay" />
            <Dialog.Content className="dialog-content concept-dialog">
              <Dialog.Title>Better Together — concept artwork</Dialog.Title>
              <Dialog.Description>
                Visual inspiration only. This is not a physical product or the
                generated demo model.
              </Dialog.Description>
              <img
                src="/better-together-concept.png"
                alt="Full Better Together concept artwork supplied in the product brief"
              />
              <Dialog.Close className="dialog-close" aria-label="Close artwork">
                <X />
              </Dialog.Close>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
      <div className="gallery-bottom">
        <div className="gallery-thumbnails">
          <button
            aria-label="Show couple detail"
            aria-pressed={!full}
            className={!full ? "selected" : ""}
            onClick={() => setFull(false)}
          >
            <img src="/better-together-concept.png" alt="Couple detail" />
          </button>
          <button
            aria-label="Show full art direction"
            aria-pressed={full}
            className={full ? "selected" : ""}
            onClick={() => setFull(true)}
          >
            <ImageIcon size={22} />
          </button>
        </div>
        <p>
          <Box size={16} /> A little idea, with a lot of heart.
        </p>
      </div>
    </div>
  );
}
