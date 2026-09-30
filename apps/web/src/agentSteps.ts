/** Human-readable label for an agent tool call in the timeline. */
export function describeStep(name: string, input: Record<string, unknown>): string {
  const q = typeof input.query === 'string' ? `“${input.query}”` : ''
  switch (name) {
    case 'predict_team':
      return 'Predict the team with the routing model'
    case 'search_similar_incidents':
      return `Search past incidents ${q}`
    case 'search_knowledge_base':
      return `Search the knowledge base ${q}`
    case 'check_recent_activity': {
      const where = input.location === 'any' ? 'all sites' : String(input.location)
      return `Check recent ${String(input.subcategory)} activity at ${where}`
    }
    default:
      return name
  }
}
