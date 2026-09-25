import { motion } from 'framer-motion';
import { Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { ClaimAttachment } from '../types';

/** Thumbnail grid with a lightbox. Shared by the customer portal and the back-office claim view. */
export function PhotoGallery({
  photos,
  onRemove,
}: {
  photos: ClaimAttachment[];
  onRemove?: (id: string) => void;
}) {
  const [open, setOpen] = useState<ClaimAttachment | null>(null);

  if (!photos.length) return null;

  return (
    <>
      <div className="thumbGrid">
        {photos.map((photo, index) => (
          <motion.div
            animate={{ opacity: 1, scale: 1 }}
            initial={{ opacity: 0, scale: 0.9 }}
            key={photo.id}
            style={{ position: 'relative' }}
            transition={{ delay: Math.min(index * 0.04, 0.3) }}
          >
            <button className="thumb" onClick={() => setOpen(photo)} type="button">
              <img alt={photo.label} src={photo.data_uri} />
              <span className="thumbTag">{photo.label}</span>
            </button>
            {onRemove ? (
              <button
                aria-label={`Remove ${photo.label}`}
                className="thumbDrop"
                onClick={() => onRemove(photo.id)}
                type="button"
              >
                <Trash2 size={11} />
              </button>
            ) : null}
          </motion.div>
        ))}
      </div>

      {open ? (
        <div className="lightbox" onClick={() => setOpen(null)} role="presentation">
          <motion.div
            animate={{ opacity: 1, scale: 1 }}
            className="lightboxInner"
            initial={{ opacity: 0, scale: 0.94 }}
            onClick={(event) => event.stopPropagation()}
            transition={{ duration: 0.18 }}
          >
            <img alt={open.label} src={open.data_uri} />
            <div className="lightboxBar">
              <div>
                <b>{open.label}</b>
                <small>
                  {open.ai_tags.join(' · ')} — uploaded {open.uploaded_at} by {open.source}
                </small>
              </div>
              <button className="btn secondary small" onClick={() => setOpen(null)} type="button">
                <X size={13} /> Close
              </button>
            </div>
          </motion.div>
        </div>
      ) : null}
    </>
  );
}
