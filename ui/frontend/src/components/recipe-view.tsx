import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import type {
  RecipeData,
  Instruction,
  HowToStep,
  HowToSection,
} from '@/types'

function parseDuration(iso: string | null | undefined): string {
  if (!iso) return ''
  const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/)
  if (!m) return iso
  const h = parseInt(m[1] ?? '0')
  const min = parseInt(m[2] ?? '0')
  const parts: string[] = []
  if (h) parts.push(`${h} hr`)
  if (min) parts.push(`${min} min`)
  return parts.join(' ') || iso
}

function toStringArray(val: string[] | string | null | undefined): string[] {
  if (!val) return []
  if (Array.isArray(val)) return val
  return [val]
}

function isHowToSection(inst: Instruction): inst is HowToSection {
  return typeof inst === 'object' && inst['@type'] === 'HowToSection'
}

function isHowToStep(inst: Instruction): inst is HowToStep {
  return typeof inst === 'object' && inst['@type'] === 'HowToStep'
}

interface StepListProps {
  instructions: Instruction[]
}

function StepList({ instructions }: StepListProps) {
  let counter = 0
  return (
    <ol className="space-y-2">
      {instructions.map((inst, i) => {
        if (isHowToSection(inst)) {
          return (
            <li key={i}>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {inst.name}
              </p>
              <ol className="space-y-1.5 pl-2">
                {inst.itemListElement.map((step, j) => {
                  counter++
                  const n = counter
                  return (
                    <li key={j} className="flex gap-2">
                      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                        {n}
                      </span>
                      <span>{step.text}</span>
                    </li>
                  )
                })}
              </ol>
            </li>
          )
        }
        counter++
        const n = counter
        const text = isHowToStep(inst) ? inst.text : inst
        return (
          <li key={i} className="flex gap-2">
            <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
              {n}
            </span>
            <span>{text}</span>
          </li>
        )
      })}
    </ol>
  )
}

interface RecipeViewProps {
  recipe: RecipeData
}

export function RecipeView({ recipe }: RecipeViewProps) {
  const prepTime = parseDuration(recipe.prepTime)
  const cookTime = parseDuration(recipe.cookTime)
  const totalTime = parseDuration(recipe.totalTime)

  const structuredIngredients = recipe.recipeIngredients ?? []
  const flatIngredients = recipe.recipeIngredient ?? []
  const hasStructured = structuredIngredients.length > 0

  const categories = toStringArray(recipe.recipeCategory)
  const cuisines = toStringArray(recipe.recipeCuisine)
  const keywords = toStringArray(recipe.keywords)
    .flatMap((k) => k.split(',').map((s) => s.trim()))
    .filter(Boolean)

  const nutrition = recipe.nutrition
  const nutritionChips: { label: string; value: string }[] = []
  if (nutrition) {
    if (nutrition.calories) nutritionChips.push({ label: 'Calories', value: nutrition.calories })
    if (nutrition.proteinContent) nutritionChips.push({ label: 'Protein', value: nutrition.proteinContent })
    if (nutrition.fatContent) nutritionChips.push({ label: 'Fat', value: nutrition.fatContent })
    if (nutrition.carbohydrateContent) nutritionChips.push({ label: 'Carbs', value: nutrition.carbohydrateContent })
    if (nutrition.fiberContent) nutritionChips.push({ label: 'Fiber', value: nutrition.fiberContent })
    if (nutrition.sugarContent) nutritionChips.push({ label: 'Sugar', value: nutrition.sugarContent })
    if (nutrition.sodiumContent) nutritionChips.push({ label: 'Sodium', value: nutrition.sodiumContent })
  }

  return (
    <ScrollArea className="max-h-[60vh]">
      <div className="space-y-4 pr-2">
        <div>
          <h2 className="text-lg font-semibold">{recipe.name}</h2>
          {recipe.description && (
            <p className="mt-1 text-sm text-muted-foreground">{recipe.description}</p>
          )}
        </div>

        {(recipe.recipeYield || prepTime || cookTime || totalTime) && (
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            {recipe.recipeYield && (
              <span>
                <span className="font-medium text-foreground">Yield</span>{' '}
                {recipe.recipeYield}
              </span>
            )}
            {prepTime && (
              <span>
                <span className="font-medium text-foreground">Prep</span>{' '}
                {prepTime}
              </span>
            )}
            {cookTime && (
              <span>
                <span className="font-medium text-foreground">Cook</span>{' '}
                {cookTime}
              </span>
            )}
            {totalTime && (
              <span>
                <span className="font-medium text-foreground">Total</span>{' '}
                {totalTime}
              </span>
            )}
          </div>
        )}

        {(categories.length > 0 || cuisines.length > 0 || keywords.length > 0) && (
          <div className="flex flex-wrap gap-1">
            {categories.map((c) => (
              <Badge key={c} variant="secondary">{c}</Badge>
            ))}
            {cuisines.map((c) => (
              <Badge key={c} variant="outline">{c}</Badge>
            ))}
            {keywords.map((k) => (
              <Badge key={k} variant="ghost">{k}</Badge>
            ))}
          </div>
        )}

        <Separator />

        {(hasStructured || flatIngredients.length > 0) && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Ingredients</h3>
            {hasStructured ? (
              <div className="space-y-2">
                {(() => {
                  let lastGroup: string | null = null
                  return structuredIngredients.map((ing, i) => {
                    const showHeading = ing.group && ing.group !== lastGroup
                    lastGroup = ing.group || lastGroup
                    return (
                      <div key={i}>
                        {showHeading && (
                          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {ing.group}
                          </p>
                        )}
                        <div className="flex gap-1 text-sm">
                          <span className="font-medium text-foreground">
                            {[ing.quantity, ing.unit].filter(Boolean).join('\u00a0')}
                          </span>
                          <span className="text-muted-foreground">
                            {ing.food}
                            {ing.notes ? ` (${ing.notes})` : ''}
                          </span>
                        </div>
                      </div>
                    )
                  })
                })()}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                {flatIngredients.map((ing, i) => (
                  <p key={i} className="text-sm">{ing}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {recipe.recipeInstructions && recipe.recipeInstructions.length > 0 && (
          <>
            <Separator />
            <div>
              <h3 className="mb-2 text-sm font-semibold">Instructions</h3>
              <StepList instructions={recipe.recipeInstructions} />
            </div>
          </>
        )}

        {nutritionChips.length > 0 && (
          <>
            <Separator />
            <div>
              <h3 className="mb-2 text-sm font-semibold">Nutrition</h3>
              <div className="flex flex-wrap gap-2">
                {nutritionChips.map(({ label, value }) => (
                  <div
                    key={label}
                    className="rounded-lg bg-muted px-2 py-1 text-xs"
                  >
                    <span className="text-muted-foreground">{label}: </span>
                    <span className="font-medium">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </ScrollArea>
  )
}
