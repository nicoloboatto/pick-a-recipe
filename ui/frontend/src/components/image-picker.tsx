import { StarIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { CandidateImage } from '@/types'

interface ImagePickerProps {
  images: CandidateImage[]
  value: number
  onChange: (index: number) => void
}

export function ImagePicker({ images, value, onChange }: ImagePickerProps) {
  if (images.length === 0) return null

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        Select the best photo for your recipe
        {images.some((i) => i.is_best) && (
          <span className="ml-1">
            (<StarIcon className="inline size-3 text-amber-500" /> = AI pick)
          </span>
        )}
      </p>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {images.map((img) => (
          <button
            key={img.index}
            type="button"
            onClick={() => onChange(img.index)}
            className={cn(
              'relative aspect-square overflow-hidden rounded-lg ring-2 transition-all focus-visible:outline-none focus-visible:ring-ring',
              img.index === value
                ? 'ring-primary'
                : 'ring-transparent hover:ring-muted-foreground/40',
            )}
          >
            <img
              src={`data:image/jpeg;base64,${img.data}`}
              alt={`Dish candidate ${img.index + 1}`}
              className="size-full object-cover"
            />
            {img.is_best && (
              <span className="absolute top-1 right-1 rounded-full bg-amber-500 p-0.5">
                <StarIcon className="size-3 text-white" />
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
