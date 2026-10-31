import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ScrollTextIcon, Undo2Icon } from 'lucide-react'

import { api } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

type PromptName = 'structuring' | 'vision'
type PromptKey = 'custom_structuring_prompt' | 'custom_vision_prompt'

const PROMPTS: { name: PromptName; key: PromptKey; label: string; hint: string; rows: number }[] = [
  {
    name: 'structuring',
    key: 'custom_structuring_prompt',
    label: 'Structuring prompt',
    hint: 'Turns the transcript, on-screen text, caption, and any linked recipe page into structured recipe fields.',
    rows: 12,
  },
  {
    name: 'vision',
    key: 'custom_vision_prompt',
    label: 'On-screen text prompt',
    hint: 'Extracts on-screen text (ingredients, instructions, captions) from video frames.',
    rows: 8,
  },
]

/**
 * Editable LLM guidance. Each prompt shows the saved override, or the in-code
 * default when there is none; the fixed suffix the app depends on is shown
 * read-only and always appended server-side.
 */
export function PromptsCard({
  get,
  set,
}: {
  get: (key: PromptKey) => string
  set: (key: PromptKey, value: string) => void
}) {
  const queryClient = useQueryClient()
  const [resetting, setResetting] = useState<PromptName | null>(null)
  const { data: defaults } = useQuery({
    queryKey: ['promptDefaults'],
    queryFn: () => api.promptDefaults(),
  })

  async function handleReset(name: PromptName, key: PromptKey) {
    setResetting(name)
    try {
      // Clears the override server-side rather than saving today's default
      // text, so the prompt keeps tracking future in-code improvements.
      const result = await api.resetPrompt(name)
      set(key, result.default_text)
      toast.success('Prompt reset to default')
      await queryClient.invalidateQueries({ queryKey: ['config'] })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to reset prompt')
    } finally {
      setResetting(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScrollTextIcon className="size-4" />
          Prompts
        </CardTitle>
        <CardDescription>
          Tune the wording sent to the model without editing code. The fixed part
          below each prompt keeps the output in the shape the app needs, and is
          always appended.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {PROMPTS.map(({ name, key, label, hint, rows }) => {
          const value = get(key) || defaults?.[name].default_text || ''
          return (
            <div key={name} className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor={key}>{label}</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={resetting !== null}
                  onClick={() => handleReset(name, key)}
                >
                  <Undo2Icon className="size-3.5" />
                  Reset to default
                </Button>
              </div>
              <Textarea
                id={key}
                rows={rows}
                spellCheck={false}
                className="font-mono text-xs max-h-96 overflow-y-auto"
                value={value}
                onChange={e => set(key, e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{hint}</p>
              {defaults && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-muted-foreground">
                    Fixed suffix (always appended, read-only)
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-2 font-mono">
                    {defaults[name].fixed_suffix}
                  </pre>
                </details>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
