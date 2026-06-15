export interface ResearchMission {
  id: string
  title: string
  query: string
  notebook_id?: string
  status: 'planning' | 'researching' | 'reflecting' | 'writing' | 'completed' | 'failed' | 'paused'
  depth: 'quick' | 'comprehensive' | 'exhaustive'
  plan?: Record<string, unknown>
  report?: string
  summary?: string
  execution_log?: Array<{phase: string; agent: string; message: string; timestamp?: string; details?: Record<string, unknown>}>
  model_override?: string
  progress: number
  error_message?: string
  created?: string
  updated?: string
}

export interface ResearchNote {
  id: string
  mission_id: string
  phase: string
  content: string
  source_type?: string
  source_url?: string
  metadata?: Record<string, unknown>
  created?: string
}

export interface CreateMissionRequest {
  query: string
  notebook_id?: string
  title?: string
  depth?: string
  model_override?: string
}
